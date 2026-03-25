#include "py_gil_stat.h"
#include "Python.h"
#include "python_util.h"
#include "time_util.h"
#include <cstdio>
#include <pthread.h>
#include <signal.h>
#include <sstream>
#include <stdlib.h>
#include <string.h>

struct bootstate {
  PyInterpreterState *interp;
  PyGilStat *stat;
};

static unsigned long pthread_t_to_ulong(pthread_t p) {
#if SIZEOF_PTHREAD_T <= SIZEOF_LONG
  return (unsigned long)p;
#else
  return (unsigned long)*(unsigned long *)&p;
#endif
}

PyGilStat::PyGilStat() {
  stat_map = new std::unordered_map<pthread_t, gil_statistics *>();
  warning_list = new std::list<gil_warning *>();
  config = nullptr;
  stat_thread_id = 0;
  running_flag = false;
  py_out_queue = NULL;
  pthread_mutex_init(&queue_mutex, NULL);
  pthread_mutex_init(&stat_map_mutex, NULL);
  pthread_mutex_init(&warning_list_mutex, NULL);
}

int PyGilStat::start(gil_monitor_config *config) {
  this->config = config;
  this->running_flag = true;
  this->start_python_stat_thread();
  return 0;
}

int PyGilStat::stop() {
  if (this->running_flag == false || stat_thread_id <= 0) {
    return 0;
  }
  send_end();
  set_out_queue(NULL);
  this->running_flag = false;
  void *retval;

  pthread_mutex_lock(&stat_map_mutex);
  stat_map->clear();
  pthread_mutex_unlock(&stat_map_mutex);

  pthread_mutex_lock(&warning_list_mutex);
  this->warning_list->clear();
  pthread_mutex_unlock(&warning_list_mutex);

  if (pthread_join((pthread_t)stat_thread_id, &retval) != 0) {
    fprintf(stderr, "[*] gil_statistics thread join failed\n");
    return -1;
  }
  return 0;
}

void PyGilStat::set_out_queue(PyObject *out_queue) {
  pthread_mutex_lock(&queue_mutex);

  if (this->py_out_queue != NULL) {
    // clear old queue
    Py_DECREF(this->py_out_queue);
  }

  if (out_queue != NULL) {
    Py_INCREF(out_queue);
    this->py_out_queue = out_queue;
  } else {
    this->py_out_queue = NULL;
  }

  pthread_mutex_unlock(&queue_mutex);
}

void PyGilStat::send(const char *msg, PyThreadState *tstate) {
  pthread_mutex_lock(&queue_mutex);
  // take gil and set current PyThreadState
  PyEval_AcquireThread(tstate);

  PyObject *result =
      PyObject_CallMethod(py_out_queue, "output_msgstr_nowait", "(is)", 0, msg);
  if (result != NULL) {
    Py_DECREF(result);
  }

  // drop gil and reset current PyThreadState
  PyEval_ReleaseThread(tstate);

  pthread_mutex_unlock(&queue_mutex);
}

void PyGilStat::send_end() {
  pthread_mutex_lock(&queue_mutex);
  // take gil
  PyGILState_STATE gstate = PyGILState_Ensure();

  PyObject *result = PyObject_CallMethod(py_out_queue, "output_msgstr_nowait",
                                         "(iO)", 1, Py_None);
  if (result != NULL) {
    Py_DECREF(result);
  }

  // drop gil
  PyGILState_Release(gstate);
  pthread_mutex_unlock(&queue_mutex);
}

std::map<unsigned long, char *> *
PyGilStat::dump_thread_name(void *boot_raw, PyThreadState *tstate) {
  // take gil and set current PyThreadState
  PyEval_AcquireThread(tstate);
  std::map<unsigned long, char *> *thread_name_map = NULL;
  // call threading.enumerate() to get all thread name
  PyObject *result = invoke_module_function("threading", "enumerate", NULL);
  if (result != NULL) {
    Py_ssize_t size = PyList_Size(result);
    if (size > 0) {
      thread_name_map = new std::map<unsigned long, char *>();
      for (int i = 0; i < size; i++) {
        // PyList_GetItem do not need to Py_DECREF
        PyObject *thread = PyList_GetItem(result, i);
        if (thread != NULL) {
          PyObject *name = PyObject_GetAttrString(thread, "_name");
          if (name != NULL) {
            Py_ssize_t str_size;
            const char *thread_name = PyUnicode_AsUTF8AndSize(name, &str_size);
            char *name_buffer = (char *)malloc(str_size + 1);
            strcpy(name_buffer, thread_name);
            Py_DECREF(name);

            PyObject *ident = PyObject_GetAttrString(thread, "_ident");
            if (ident != NULL) {
              unsigned long thread_id = PyLong_AsUnsignedLong(ident);
              Py_DECREF(ident);
              thread_name_map->insert(
                  std::map<unsigned long, char *>::value_type(thread_id,
                                                              name_buffer));
            }
          }
        }
      }
    }
    Py_DECREF(result);
  }

  // drop gil and reset current PyThreadState
  PyEval_ReleaseThread(tstate);

  return thread_name_map;
}

void PyGilStat::dump_gil_stat(
    void *boot_raw, PyThreadState *tstate,
    std::map<unsigned long, char *> *thread_name_map) {
  struct bootstate *boot = (struct bootstate *)boot_raw;
  PyGilStat *stat = boot->stat;
  int nthreads = 0;

  gil_statistics *stats[stat->config->gil_stat_max_threads];
  pthread_t thread_ids[stat->config->gil_stat_max_threads];
  char thread_name_buffer[16];

  char time_buffer[24];
  struct timespec ts;
  timespec_get(&ts, TIME_UTC);
  strftime_with_millisec(&ts, time_buffer, 24);

  pthread_mutex_lock(&stat->stat_map_mutex);
  // stat map iteration should be fast
  for (std::unordered_map<pthread_t, gil_statistics *>::iterator it =
           stat->stat_map->begin();
       it != stat->stat_map->end(); ++it) {
    if (nthreads > stat->config->gil_stat_max_threads) {
      break;
    }
    gil_statistics *gil_stat = it->second;
    if (gil_stat->gil_take_count > 0 && gil_stat->gil_drop_count > 0) {
      gil_statistics *copy_gil_stat =
          (gil_statistics *)malloc(sizeof(gil_statistics));
      memcpy(copy_gil_stat, gil_stat, sizeof(gil_statistics));
      stats[nthreads] = copy_gil_stat;
      thread_ids[nthreads] = it->first;

      nthreads++;
    }
  }
  pthread_mutex_unlock(&stat->stat_map_mutex);

  // print with no lock
  if (nthreads > 0) {
    std::stringstream ss;
    char str_buffer[4096];
    sprintf(
        str_buffer,
        "\ngil statistics "
        "report:\n%-26s%-18s%-24s%-12s%-18s%-12s%-18s%-12s%-12s%-18s%-12s\n",
        "time", "thread_id", "thread_name", "takecnt", "hold_all(ns)",
        "holdavg(ns)", "take_all(ns)", "takeavg(ns)", "dropcnt", "drop_all(ns)",
        "dropavg(ns)");

    ss << str_buffer;

    for (int i = 0; i < nthreads; i++) {
      gil_statistics *gil_stat = stats[i];
      unsigned long pid = pthread_t_to_ulong(thread_ids[i]);

      const char *name_ptr = NULL;
      if (thread_name_map != NULL) {
        auto it = thread_name_map->find(pid);
        if (it != thread_name_map->end()) {
          name_ptr = it->second;
        }
      }
      if (name_ptr == NULL) {
        pthread_getname_np(thread_ids[i], thread_name_buffer,
                           sizeof(thread_name_buffer));
        name_ptr = (const char *)&thread_name_buffer;
      }

      sprintf(
          str_buffer,
          "%-26s%-18lx%-24s%-12lu%-18lu%-12lu%-18lu%-12lu%-12lu%-18lu%-12lu\n",
          time_buffer, pid, name_ptr, gil_stat->gil_take_count,
          gil_stat->gil_hold_total,
          gil_stat->gil_hold_total / gil_stat->gil_take_count,
          gil_stat->gil_take_total_cost,
          gil_stat->gil_take_total_cost / gil_stat->gil_take_count,
          gil_stat->gil_drop_count, gil_stat->gil_drop_total_cost,
          gil_stat->gil_drop_total_cost / gil_stat->gil_drop_count);
      ss << str_buffer;
      free(gil_stat);
    }

    ss << "\n";
    const std::string tmp = ss.str();
    const char *cstr = tmp.c_str();
    // send to server q, here will take gil lock then send then release gil lock
    stat->send(cstr, tstate);
  }

  // remove exited thread id from thread map
  for (int i = 0; i < nthreads; i++) {
    pthread_t p = thread_ids[i];
    // kill -0 test thread alive
    int ret = pthread_kill(p, 0);
    if (ret != 0 && ret != EBUSY) {
      pthread_mutex_lock(&stat->stat_map_mutex);
      auto it = stat->stat_map->find(p);
      if (it != stat->stat_map->end()) {
        gil_statistics *gil_stat = it->second;
        stat->stat_map->erase(p);
        free(gil_stat);
      }
      pthread_mutex_unlock(&stat->stat_map_mutex);
    }
  }
}

void PyGilStat::dump_gil_warning(
    void *boot_raw, PyThreadState *tstate,
    std::map<unsigned long, char *> *thread_name_map) {
  struct bootstate *boot = (struct bootstate *)boot_raw;
  PyGilStat *stat = boot->stat;

  pthread_mutex_lock(&stat->warning_list_mutex);
  if (stat->warning_list->size() > 0) {
    std::stringstream ss;
    char str_buffer[4096];
    sprintf(str_buffer,
            "\ngil warning report:\n%-26s%-18s%-24s%-12s%-18s%-18s%-30s%-30s\n",
            "time", "thread_id", "thread_name", "event", "cost(ns)",
            "threshold(ns)", "start(ns)", "end(ns)");
    ss << str_buffer;

    while (stat->warning_list->size() > 0) {
      gil_warning *w = stat->warning_list->front();
      stat->warning_list->pop_front();

      unsigned long pid = pthread_t_to_ulong(w->thread_id);
      const char *name_ptr = NULL;
      if (thread_name_map != NULL) {
        auto it = thread_name_map->find(pid);
        if (it != thread_name_map->end()) {
          name_ptr = it->second;
        }
      }
      if (name_ptr == NULL) {
        name_ptr = (const char *)&w->thread_name;
      }

      sprintf(str_buffer, "%-26s%-18lx%-24s%-12s%-18lu%-18lu%-30lu%-30lu\n",
              w->time, pid, name_ptr, w->type == 0 ? "take_gil" : "hold_gil",
              w->cost,
              w->type == 0 ? stat->config->gil_take_warning_threshold
                           : stat->config->gil_hold_warning_threshold,
              w->start_ns, w->end_ns);
      free(w);
      ss << str_buffer;
    }

    pthread_mutex_unlock(&stat->warning_list_mutex);

    ss << "\n";
    const std::string tmp = ss.str();
    const char *cstr = tmp.c_str();
    // send to server q, here will take gil lock then send then release gil lock
    stat->send(cstr, tstate);

  } else {
    pthread_mutex_unlock(&stat->warning_list_mutex);
  }
}

/**
 * similar to python vm _threadmodule.c thread_run func
 */
void PyGilStat::boot_entry(void *boot_raw) {
  struct bootstate *boot = (struct bootstate *)boot_raw;
  PyGilStat *stat = boot->stat;

#if defined(__APPLE__)
  pthread_setname_np("gil_stat");
#else
  pthread_setname_np(pthread_self(), "gil_stat");
#endif
  // pystate.h
  // here will call _PyThreadState_Init
  PyThreadState *tstate = PyThreadState_New(boot->interp);
  if (tstate == NULL) {
    PyMem_DEL(boot_raw);
    fprintf(stderr,
            "[PyFlightProfiler] Not enough memory to create thread state.\n");
    return;
  }

  fprintf(stdout, "[PyFlightProfiler] Gil Stat Thread start Executing.\n");

  int stat_interval = stat->config->stat_interval * 1000;
  int sleep_interval = 500;
  struct timespec last_ts;
  timespec_get(&last_ts, TIME_UTC);
  while (stat->running_flag) {
    struct timespec ts;
    timespec_get(&ts, TIME_UTC);
    if ((ts.tv_sec - last_ts.tv_sec) * 1000 +
            (ts.tv_nsec - last_ts.tv_nsec) / 1000000 >=
        stat_interval) {
      // dump all thread id-name pair, because python Thread's name is not
      // setted to pthread
      std::map<unsigned long, char *> *thread_name_map =
          PyGilStat::dump_thread_name(boot_raw, tstate);
      PyGilStat::dump_gil_warning(boot_raw, tstate, thread_name_map);
      PyGilStat::dump_gil_stat(boot_raw, tstate, thread_name_map);
      // release thread name map
      if (thread_name_map != NULL) {
        for (std::map<unsigned long, char *>::iterator it =
                 thread_name_map->begin();
             it != thread_name_map->end(); ++it) {
          free(it->second);
        }
        delete thread_name_map;
      }

      timespec_get(&last_ts, TIME_UTC);
      continue;
    }
    // sleep
    struct timeval t;
    t.tv_sec = sleep_interval / 1000;
    t.tv_usec = (sleep_interval % 1000) * 1000;
    select(0, (fd_set *)0, (fd_set *)0, (fd_set *)0, &t);
  }

  fprintf(stdout, "[PyFlightProfiler] Gil Stat Thread finished execution.\n");

  PyMem_RawFree(boot_raw);

  // ceval.h
  // here take gil lock, and set current PyThreadState
  PyEval_AcquireThread(tstate);
  // clear tstat data
  PyThreadState_Clear(tstate);
  // here will reset current PyThreadState, release gil lock and delete
  // PyThreadState mem
  PyThreadState_DeleteCurrent();
}

void PyGilStat::start_python_stat_thread() {
  struct bootstate *boot;
  unsigned long ident;

  // pymem.h
  // here use PyMem_RawMalloc instead of PyMem_NEW or PyMem_Malloc
  // PyMem_NEW or PyMem_Malloc not work in python 3.12
  boot = (struct bootstate *)PyMem_RawMalloc(sizeof(struct bootstate));
  if (boot == NULL) {
    fprintf(stderr,
            "[PyFlightProfiler] alloc memory for gil stat bootstate failed\n");
    PyErr_PrintEx(0);
    return;
  }

  // init if not yet done
  PyThread_init_thread();

  // Ensure that the current thread is ready to call the Python C API
  // here will call PyThreadState_New, take gil and set current thread state
  PyGILState_STATE old_gil_state = PyGILState_Ensure();

  boot->interp = PyThreadState_Get()->interp;
  boot->stat = this;

  // start a background thread to inject code, gdb will quit quickly
  ident = PyThread_start_new_thread(PyGilStat::boot_entry, (void *)boot);

  if (ident == PYTHREAD_INVALID_THREAD_ID) {
    PyMem_RawFree(boot);
  } else {
    this->stat_thread_id = ident;
  }

  // here will call PyThreadState_Clear and PyThreadState_DeleteCurrent(drop
  // gil)
  PyGILState_Release(old_gil_state);
}

void PyGilStat::on_take_gil_enter(pthread_t p) {
  pthread_mutex_lock(&stat_map_mutex);
  auto it = this->stat_map->find(p);
  gil_statistics *gil_stat;
  if (it != this->stat_map->end()) {
    gil_stat = it->second;
  } else {
    gil_stat = (gil_statistics *)malloc(sizeof(gil_statistics));
    memset(gil_stat, 0, sizeof(gil_statistics));
    this->stat_map->insert(
        std::unordered_map<pthread_t, gil_statistics *>::value_type(p,
                                                                    gil_stat));
  }
  timespec_get(&gil_stat->last_gil_take_start_time, TIME_UTC);
  pthread_mutex_unlock(&stat_map_mutex);
}

void PyGilStat::on_take_gil_leave(pthread_t p) {
  pthread_mutex_lock(&stat_map_mutex);
  auto it = this->stat_map->find(p);
  gil_statistics *gil_stat;
  if (it != this->stat_map->end()) {
    gil_stat = it->second;
    if (gil_stat->last_gil_take_start_time.tv_sec <= 0) {
      pthread_mutex_unlock(&stat_map_mutex);
      fprintf(
          stderr,
          "[*] gil_statistics last take start not found when take_gil leave\n");
      return;
    }
    timespec_get(&gil_stat->last_gil_take_success_time, TIME_UTC);
    gil_stat->gil_take_count++;
    gil_stat->last_gil_take_cost =
        (gil_stat->last_gil_take_success_time.tv_sec -
         gil_stat->last_gil_take_start_time.tv_sec) *
            1000000000ul +
        gil_stat->last_gil_take_success_time.tv_nsec -
        gil_stat->last_gil_take_start_time.tv_nsec;
    gil_stat->gil_take_total_cost += gil_stat->last_gil_take_cost;
    pthread_mutex_unlock(&stat_map_mutex);
  } else {
    pthread_mutex_unlock(&stat_map_mutex);
    fprintf(stderr, "[*] gil_statistics not found when take_gil leave\n");
  }
}

void PyGilStat::on_drop_gil_enter(pthread_t p) {
  pthread_mutex_lock(&stat_map_mutex);
  auto it = this->stat_map->find(p);
  gil_statistics *gil_stat;
  if (it != this->stat_map->end()) {
    gil_stat = it->second;
    timespec_get(&gil_stat->last_gil_drop_start_time, TIME_UTC);
    pthread_mutex_unlock(&stat_map_mutex);
  } else {
    pthread_mutex_unlock(&stat_map_mutex);
    fprintf(stderr, "[*] gil_statistics not found when drop_gil enter\n");
  }
}

void PyGilStat::on_drop_gil_leave(pthread_t p) {
  pthread_mutex_lock(&stat_map_mutex);
  auto it = this->stat_map->find(p);
  gil_statistics *gil_stat;
  if (it != this->stat_map->end()) {
    gil_stat = it->second;

    if (gil_stat->last_gil_take_start_time.tv_sec <= 0 ||
        gil_stat->last_gil_take_success_time.tv_sec <= 0) {
      pthread_mutex_unlock(&stat_map_mutex);
      fprintf(stderr,
              "[*] gil_statistics last take not found when drop_gil leave\n");
      return;
    }

    if (gil_stat->last_gil_drop_start_time.tv_sec <= 0) {
      pthread_mutex_unlock(&stat_map_mutex);
      fprintf(
          stderr,
          "[*] gil_statistics last drop start not found when drop_gil leave\n");
      return;
    }

    unsigned long last_gil_drop_cost;
    unsigned long last_gil_hold_time;
    struct timespec last_gil_drop_success_time;
    timespec_get(&last_gil_drop_success_time, TIME_UTC);
    gil_stat->gil_drop_count++;
    last_gil_drop_cost = (last_gil_drop_success_time.tv_sec -
                          gil_stat->last_gil_drop_start_time.tv_sec) *
                             1000000000ul +
                         last_gil_drop_success_time.tv_nsec -
                         gil_stat->last_gil_drop_start_time.tv_nsec;
    gil_stat->gil_drop_total_cost += last_gil_drop_cost;
    last_gil_hold_time = (last_gil_drop_success_time.tv_sec -
                          gil_stat->last_gil_take_success_time.tv_sec) *
                             1000000000ul +
                         last_gil_drop_success_time.tv_nsec -
                         gil_stat->last_gil_take_success_time.tv_nsec;
    gil_stat->gil_hold_total += last_gil_hold_time;

    pthread_mutex_unlock(&stat_map_mutex);

    // thread take gil mutex cost time warning
    if (gil_stat->last_gil_take_cost >
        config->gil_take_warning_threshold * 1000000ul) {

      gil_warning *w = (gil_warning *)malloc(sizeof(gil_warning));
      strftime_with_millisec(&gil_stat->last_gil_take_success_time, w->time,
                             sizeof(w->time));
      w->thread_id = p;
      pthread_getname_np(p, w->thread_name, sizeof(w->thread_name));
      w->type = 0;
      w->cost = gil_stat->last_gil_take_cost;
      w->start_ns = gil_stat->last_gil_take_start_time.tv_sec * 1000000000ul +
                    gil_stat->last_gil_take_start_time.tv_nsec;
      w->end_ns = gil_stat->last_gil_take_success_time.tv_sec * 1000000000ul +
                  gil_stat->last_gil_take_success_time.tv_nsec;

      pthread_mutex_lock(&warning_list_mutex);
      if (this->warning_list->size() > 50) {
        gil_warning *deprecated = this->warning_list->front();
        this->warning_list->pop_front();
        free(deprecated);
      }
      this->warning_list->push_back(w);
      pthread_mutex_unlock(&warning_list_mutex);
    }

    // thread hold gil mutex time warning
    if (last_gil_hold_time > config->gil_hold_warning_threshold * 1000000ul) {
      gil_warning *w = (gil_warning *)malloc(sizeof(gil_warning));
      strftime_with_millisec(&gil_stat->last_gil_take_success_time, w->time,
                             sizeof(w->time));

      pthread_getname_np(p, w->thread_name, sizeof(w->thread_name));
      w->type = 0;
      w->cost = last_gil_hold_time;
      w->start_ns = gil_stat->last_gil_take_success_time.tv_sec * 1000000000ul +
                    gil_stat->last_gil_take_success_time.tv_nsec;
      w->end_ns = last_gil_drop_success_time.tv_sec * 1000000000ul +
                  last_gil_drop_success_time.tv_nsec;

      pthread_mutex_lock(&warning_list_mutex);
      if (this->warning_list->size() > 50) {
        gil_warning *deprecated = this->warning_list->front();
        this->warning_list->pop_front();
        free(deprecated);
      }
      this->warning_list->push_back(w);
      pthread_mutex_unlock(&warning_list_mutex);
    }
  } else {
    pthread_mutex_unlock(&stat_map_mutex);
    fprintf(stderr, "[*] gil_statistics not found when drop_gil leave\n");
  }
}
