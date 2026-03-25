#include "code_inject.h"
#include "Python.h"
#include "frida_profiler.h"
#include "py_gil_intercept.h"
#include "symbol_util.h"
#include <dlfcn.h>
#include <limits.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static char filename[FILENAME_MAX] = "";
static char take_gil_literal[9] = "take_gil";
static int py_injected = 0;
static int port;
static pthread_mutex_t mutex;

struct bootstate {
  PyInterpreterState *interp;
};

static PyObject *exec_python_file(FILE *fp, char *file_path, int port) {

  // dictobject.h
  PyObject *globals = PyDict_New();

  if (PyDict_SetItemString(globals, "__builtins__", PyEval_GetBuiltins()) !=
      0) {
    return NULL;
  }

  if (PyDict_SetItemString(globals, "__profile_listen_port__",
                           PyLong_FromLong(port)) != 0) {
    return NULL;
  }

  if (PyDict_SetItemString(globals, "__file__",
                           PyUnicode_FromString(file_path)) != 0) {
    return NULL;
  }

  // pythonrun.h , here locals same to globals
  PyObject *v = PyRun_File(fp, file_path,
                           // Py_file_input from compile.h
                           Py_file_input, globals, globals);

  Py_DECREF(globals);

  return v;
}

static PyObject *exec_python_entrance() {
  FILE *fp = NULL;
  int exists;

  exists = 0;
  struct stat s;
  if (stat(filename, &s) == 0) {
    if (S_ISDIR(s.st_mode)) {
      errno = EISDIR;
    } else {
      exists = 1;
    }
  }

  if (exists) {
    Py_BEGIN_ALLOW_THREADS fp = fopen(filename, "r" PY_STDIOTEXTMODE);
    Py_END_ALLOW_THREADS

        if (fp == NULL) {
      exists = 0;
    }
  }

  if (!exists) {
    // pyerrors.h
    PyErr_SetFromErrnoWithFilename(PyExc_IOError, filename);
    return NULL;
  }

  return exec_python_file(fp, filename, port);
}

/**
 * similar to python vm _threadmodule.c thread_run func
 */
static void boot_entry(void *boot_raw) {
  struct bootstate *boot = (struct bootstate *)boot_raw;

#if defined(__APPLE__)
  pthread_setname_np("flight_profiler_agent");
#else
  pthread_setname_np(pthread_self(), "flight_profiler_agent");
#endif

  // pystate.h
  // here will call _PyThreadState_Init
  PyThreadState *tstate = PyThreadState_New(boot->interp);
  if (tstate == NULL) {
    PyMem_DEL(boot_raw);
    fprintf(stderr,
            "pyFlightProfiler: Not enough memory to create thread state.\n");
    return;
  }

  // ceval.h
  // here take gil lock, and set current PyThreadState
  PyEval_AcquireThread(tstate);

  fprintf(stdout, "pyFlightProfiler: CodeInject Executing %s.\n", filename);
  PyObject *res = exec_python_entrance();
  if (res == NULL) {
    if (PyErr_ExceptionMatches(PyExc_SystemExit)) {
      /* SystemExit is ignored silently */
      PyErr_Clear();
    } else {
      fprintf(stderr, "pyFlightProfiler: Unhandled exception in thread.\n");
      PyErr_PrintEx(0);
      // clear state, we don't want to crash the other process
      PyErr_Clear();
    }
  } else {
    Py_DECREF(res);
  }

  fprintf(stdout, "pyFlightProfiler: Thread finished execution.\n");
  PyMem_RawFree(boot_raw);

  // clear tstat data
  PyThreadState_Clear(tstate);
  // here will reset current PyThreadState, release gil lock and delete
  // PyThreadState mem
  PyThreadState_DeleteCurrent();
}

static int start_thread() {
  struct bootstate *boot;
  unsigned long ident;

  // pymem.h
  // here use PyMem_RawMalloc instead of PyMem_NEW or PyMem_Malloc
  // PyMem_NEW or PyMem_Malloc not work in python 3.12
  boot = (struct bootstate *)PyMem_RawMalloc(sizeof(struct bootstate));
  if (boot == NULL) {
    fprintf(stderr, "pyFlightProfiler: alloc memory for bootstate failed\n");
    return 1;
  }

  // init if not yet done
  PyThread_init_thread();

  // Ensure that the current thread is ready to call the Python C API
  // here will call PyThreadState_New, take gil and set current thread state
  PyGILState_STATE old_gil_state = PyGILState_Ensure();

  boot->interp = PyThreadState_Get()->interp;
  // start a background thread to inject code, gdb will quit quickly
  ident = PyThread_start_new_thread(boot_entry, (void *)boot);

  int ret = 0;
  if (ident == PYTHREAD_INVALID_THREAD_ID) {
    PyMem_RawFree(boot);
    ret = -1;
  }

  // here will call PyThreadState_Clear and PyThreadState_DeleteCurrent(drop
  // gil)
  PyGILState_Release(old_gil_state);

  return ret;
}

#ifdef __cplusplus
extern "C" {
#endif

int inject(char *fn, int p, unsigned long nm_symbol_offset) {
  int ret_port = p;
  int ret;
  pthread_mutex_lock(&mutex);
  if (py_injected != 0) {
    fprintf(stderr, "code already injected");
    ret_port = port;
  } else {
    strcpy(filename, fn);
    port = p;
    ret = start_thread();
    if (ret != 0) {
      pthread_mutex_unlock(&mutex);
      return -1;
    }
    py_injected = 1;
  }
  pthread_mutex_unlock(&mutex);
  // init offset from proc addr to addr get from system nm command
  set_nm_symbol_offset(nm_symbol_offset);

  ret = init_frida_gum();
  if (ret != 0) {
    return -1;
  }
  return ret_port;
}

int inject_init_frida_gum(unsigned long nm_symbol_offset) {
  // used for CPython >= 3.14
  // init offset from proc addr to addr get from system nm command
  set_nm_symbol_offset(nm_symbol_offset);

  if (init_frida_gum() != 0) {
    return -1;
  }
  return 0;
}

static void get_parent_directory(char *path) {
  char *last_slash;
#ifdef _WIN32
  // For Windows, use the backslash.
  last_slash = strrchr(path, '\\');
#else
  // For Unix-like systems, use the forward slash.
  last_slash = strrchr(path, '/');
#endif
  if (last_slash) {
    *last_slash = '\0'; // Terminate the string at the last slash
  }
}

const void *get_so_path() {
  Dl_info dl_info;
  if (dladdr((void *)get_so_path, &dl_info) == 0) {
    perror("dladdr failed");
    return NULL;
  }
  return dl_info.dli_fname;
}

void inject_inner() {
  pthread_mutex_init(&mutex, NULL);

  const char *so_path = (const char *)get_so_path();
  if (so_path == NULL) {
    perror("Unable to open so path.");
    return;
  }
  char so_path_modify[PATH_MAX];

  // Copy string
  strcpy(so_path_modify, so_path);

  get_parent_directory(so_path_modify);
  char params_path[PATH_MAX]; // Make sure the buffer is large enough
  snprintf(params_path, sizeof(params_path), "%s/inject_params.data",
           so_path_modify);

  FILE *file;
  char py_code[PATH_MAX];
  char line[PATH_MAX + 30];
  int port;
  unsigned long base_addr;

  file = fopen(params_path, "r");
  if (file == NULL) {
    perror("Unable to open input_prams.data");
    return;
  }
  if (fgets(line, sizeof(line), file) != NULL) {
    line[strcspn(line, "\n")] = '\0';

    char *token = strtok(line, ",");

    if (token != NULL) {
      strncpy(py_code, token, sizeof(py_code));
      py_code[sizeof(py_code) - 1] = '\0';
      token = strtok(NULL, ",");
    }

    if (token != NULL) {
      port = atoi(token);
      token = strtok(NULL, ",");
    }

    if (token != NULL) {
      base_addr = strtoul(token, NULL, 10);
    }
  } else {
    fprintf(stderr, "Error reading input_params.data!\n");
    return;
  }
  fclose(file);
  inject(py_code, port, base_addr);
}

#ifdef __cplusplus
}
#endif

/*
 * This function is automatically called when the library is injected
 * into a process.
 */
__attribute__((constructor)) void code_inject_init() {
#if !defined(__APPLE__)
  if (Py_IsInitialized()) {
    if (Py_GetVersion() != NULL) {
      const char *version = Py_GetVersion();
      int major, minor;
      if (sscanf(version, "%d.%d", &major, &minor) == 2) {
        if (major == 3 && minor < 14) {
          inject_inner();
        }
      }
    }
  } else {
#if PY_MAJOR_VERSION == 3 && PY_MINOR_VERSION < 14
    inject_inner();
#endif
  }
#endif
}
