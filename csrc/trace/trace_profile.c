#include <Python.h>
#include <assert.h>
#include <float.h>
#include <frameobject.h>
#include <stdio.h>
#include <structmember.h>
#include <sys/time.h>

////////////////////////
// Internal functions //
////////////////////////

static long long NSEC_PER_SEC = 1e9;

static long long _get_time_ns(void) {
  struct timespec ts;
  clock_gettime(CLOCK_REALTIME, &ts);
  return (long long)ts.tv_sec * NSEC_PER_SEC + ts.tv_nsec;
}

static PyCodeObject *_code_from_frame(PyFrameObject *frame) {
#if PY_VERSION_HEX >= 0x03090000
  return PyFrame_GetCode(frame);
#else
  PyCodeObject *result = frame->f_code;
  Py_XINCREF(result);
  return result;
#endif
}

static PyObject *_get_frame_info(PyFrameObject *frame, Py_ssize_t start_ns,
                                 Py_ssize_t cost_ns, Py_ssize_t pid,
                                 PyObject *arg, int c_frame) {
  if (c_frame) {
    PyObject *qualname = PyObject_GetAttrString(arg, "__qualname__");
    if (!qualname) {
      qualname = PyObject_GetAttrString(arg, "__name__");
    }
    PyObject *result = PyUnicode_FromFormat("%U%c%s%c%i%c%lld%c%lld%c%lld",
                                            qualname, 0, "<built-in>", 0, 0, 1,
                                            start_ns, 1, cost_ns, 1, pid);
    Py_XDECREF(qualname);
    return result;
  } else {
    PyCodeObject *code = _code_from_frame(frame);
    PyObject *result = PyUnicode_FromFormat(
        "%U%c%U%c%i%c%lld%c%lld%c%lld", code->co_name, 0, code->co_filename, 0,
        code->co_firstlineno, 1, start_ns, 1, cost_ns, 1, pid);
    Py_XDECREF(code);
    return result;
  }
}

static PyObject *_get_header(PyFrameObject *frame, int c_frame, PyObject *arg) {
  if (c_frame) {
    PyObject *qualname = PyObject_GetAttrString(arg, "__qualname__");
    if (!qualname) {
      qualname = PyObject_GetAttrString(arg, "__name__");
    }
    PyObject *result =
        PyUnicode_FromFormat("%U%c%s%c%i", qualname, 0, "<built-in>", 0, 0);
    Py_XDECREF(qualname);
    return result;
  } else {
    PyCodeObject *code = _code_from_frame(frame);
    PyObject *result =
        PyUnicode_FromFormat("%U%c%U%c%i", code->co_name, 0, code->co_filename,
                             0, code->co_firstlineno);
    Py_XDECREF(code);
    return result;
  }
}

static PyObject *build_context_switch_frame(Py_ssize_t start_ns,
                                            Py_ssize_t cost_ns,
                                            Py_ssize_t pid) {
  PyObject *result =
      PyUnicode_FromFormat("%s%c%c%i%c%lld%c%lld%c%lld", "[await]", 0, 0, 0, 1,
                           start_ns, 1, cost_ns, 1, pid);
  return result;
}

static PyObject *build_last_async_frame(PyObject *frame_desp,
                                        Py_ssize_t start_ns, Py_ssize_t cost_ns,
                                        Py_ssize_t pid) {
  PyObject *result = PyUnicode_FromFormat("%U%c%lld%c%lld%c%lld", frame_desp, 1,
                                          start_ns, 1, cost_ns, 1, pid);
  return result;
}

///////////////////
// TraceProfiler //
///////////////////
typedef struct {
  PyObject_HEAD PyObject *prev; // LinkedList FrameNode
  PyObject *succ;
  Py_ssize_t start_ns;
  Py_ssize_t offset; // target frameNode in sending frame offset

  PyObject *frame_desp;
  PyObject *frame_id;
  PyObject *enter_timestamp;
} FrameNode;

typedef struct trace_profiler {
  PyObject_HEAD PyObject *target; // output message to client callable target
  PyObject *on_sending_frame;     // frames that ready to be sent
  PyObject *out_queue;            // sending queue
  FrameNode *top;                 // frame stack top
  Py_ssize_t sz;                  // frame stack size
  Py_ssize_t sf_sz;               // sending frame size
  Py_ssize_t is_async;            // async function
  long long interval;             // interval
  Py_ssize_t current_depth;       // current top depth
  Py_ssize_t depth_limit;         // depth limit
} TraceProfiler;

static void TraceProfiler_Dealloc(TraceProfiler *self) {
  if (!self->is_async) {
    FrameNode *top_frame = (FrameNode *)self->top;
    self->top = (FrameNode *)top_frame->prev;
    Py_DECREF(top_frame);
  }
  Py_XDECREF(self->top);
  self->top = NULL;
  Py_DECREF(self->on_sending_frame);
  Py_DECREF(self->target);
  Py_DECREF(self->out_queue);
  Py_TYPE(self)->tp_free(self);
}

static void FrameNode_Dealloc(FrameNode *self) {
  self->prev = NULL;
  Py_XDECREF(self->succ);
  Py_XDECREF(self->enter_timestamp);
  Py_XDECREF(self->frame_id);
  Py_XDECREF(self->frame_desp);
  Py_TYPE(self)->tp_free(self);
}

static PyTypeObject FrameNode_Type = {
    PyVarObject_HEAD_INIT(NULL, 0) "pyflight.ext.FrameNode", /* tp_name */
    sizeof(FrameNode),                                       /* tp_basicsize */
    0,                                                       /* tp_itemsize */
    (destructor)FrameNode_Dealloc,                           /* tp_dealloc */
    0,                                                       /* tp_print */
    0,                                                       /* tp_getattr */
    0,                                                       /* tp_setattr */
    0,                                                       /* tp_reserved */
    0,                                                       /* tp_repr */
    0,                                                       /* tp_as_number */
    0,                                        /* tp_as_sequence */
    0,                                        /* tp_as_mapping */
    0,                                        /* tp_hash */
    0,                                        /* tp_call */
    0,                                        /* tp_str */
    0,                                        /* tp_getattro */
    0,                                        /* tp_setattro */
    0,                                        /* tp_as_buffer */
    Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE, /* tp_flags */
    0,                                        /* tp_doc */
    0,                                        /* tp_traverse */
    0,                                        /* tp_clear */
    0,                                        /* tp_richcompare */
    0,                                        /* tp_weaklistoffset */
    0,                                        /* tp_iter */
    0,                                        /* tp_iternext */
    0,                                        /* tp_methods */
    0,                                        /* tp_members */
    0,                                        /* tp_getset */
    0,                                        /* tp_base */
    0,                                        /* tp_dict */
    0,                                        /* tp_descr_get */
    0,                                        /* tp_descr_set */
    0,                                        /* tp_dictoffset */
    0,                                        /* tp_init */
    PyType_GenericAlloc,                      /* tp_alloc */
    PyType_GenericNew,                        /* tp_new */
    PyObject_Del,                             /* tp_free */
};

static PyTypeObject TraceProfiler_Type = {
    PyVarObject_HEAD_INIT(NULL, 0) "pyflight.ext.TraceProfiler", /* tp_name */
    sizeof(TraceProfiler),                    /* tp_basicsize */
    0,                                        /* tp_itemsize */
    (destructor)TraceProfiler_Dealloc,        /* tp_dealloc */
    0,                                        /* tp_print */
    0,                                        /* tp_getattr */
    0,                                        /* tp_setattr */
    0,                                        /* tp_reserved */
    0,                                        /* tp_repr */
    0,                                        /* tp_as_number */
    0,                                        /* tp_as_sequence */
    0,                                        /* tp_as_mapping */
    0,                                        /* tp_hash */
    0,                                        /* tp_call */
    0,                                        /* tp_str */
    0,                                        /* tp_getattro */
    0,                                        /* tp_setattro */
    0,                                        /* tp_as_buffer */
    Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE, /* tp_flags */
    0,                                        /* tp_doc */
    0,                                        /* tp_traverse */
    0,                                        /* tp_clear */
    0,                                        /* tp_richcompare */
    0,                                        /* tp_weaklistoffset */
    0,                                        /* tp_iter */
    0,                                        /* tp_iternext */
    0,                                        /* tp_methods */
    0,                                        /* tp_members */
    0,                                        /* tp_getset */
    0,                                        /* tp_base */
    0,                                        /* tp_dict */
    0,                                        /* tp_descr_get */
    0,                                        /* tp_descr_set */
    0,                                        /* tp_dictoffset */
    0,                                        /* tp_init */
    PyType_GenericAlloc,                      /* tp_alloc */
    PyType_GenericNew,                        /* tp_new */
    PyObject_Del,                             /* tp_free */
};

static FrameNode *pop_last_element(PyObject *list, Py_ssize_t size) {

  PyObject *last_element = PyList_GetItem(list, size - 1);
  Py_INCREF(last_element);

  if (PyList_SetSlice(list, size - 1, size, NULL) ==
      -1) { // slice will decrease element ref cnt by 1
    Py_DECREF(last_element);
    return NULL;
  }
  return (FrameNode *)last_element;
}

static FrameNode *FrameNode_New() {
  FrameNode *node = PyObject_New(FrameNode, &FrameNode_Type);
  node->prev = NULL;
  node->succ = PyList_New(0);
  node->frame_desp = NULL;
  node->enter_timestamp = PyList_New(0);
  node->frame_id = NULL;
  return node;
}

static void TraceProfiler_PushFrame(TraceProfiler *self, Py_ssize_t start_ns) {
  FrameNode *node = FrameNode_New();
  node->prev = (PyObject *)self->top;
  node->start_ns = start_ns;
  node->offset = self->sf_sz;
  self->sz += 1;
  self->sf_sz += 1;
  self->top = node;
}

static void TraceProfiler_PushFrameWithDepth(TraceProfiler *self,
                                             Py_ssize_t start_ns) {
  FrameNode *node = FrameNode_New();
  node->prev = (PyObject *)self->top;
  node->start_ns = start_ns;
  node->offset = self->sf_sz;
  self->sz += 1;
  self->sf_sz += 1;
  self->top = node;
  self->current_depth += 1;
}

static void TraceProfiler_InnerPushAsyncFrame(TraceProfiler *self,
                                              Py_ssize_t start_ns,
                                              PyObject *frame_desp,
                                              PyObject *frame_id) {
  FrameNode *node = FrameNode_New();
  PyObject *temp_start_ns = PyLong_FromLong(start_ns);
  PyList_Append(node->enter_timestamp, temp_start_ns);
  Py_DECREF(temp_start_ns);
  node->frame_id = frame_id;

  PyList_Append(self->top->succ, (PyObject *)node);
  node->prev = (PyObject *)self->top;
  node->start_ns = start_ns;
  node->offset = self->sf_sz;
  self->sz += 1;
  self->sf_sz += 1;
  node->frame_desp = frame_desp;
  self->top = node;
  Py_DECREF(node);
}

static void TraceProfiler_InnerPushAsyncFrameWithDepth(TraceProfiler *self,
                                                       Py_ssize_t start_ns,
                                                       PyObject *frame_desp,
                                                       PyObject *frame_id) {
  FrameNode *node = FrameNode_New();
  PyObject *temp_start_ns = PyLong_FromLong(start_ns);
  PyList_Append(node->enter_timestamp, temp_start_ns);
  Py_DECREF(temp_start_ns);
  node->frame_id = frame_id;

  PyList_Append(self->top->succ, (PyObject *)node);
  node->prev = (PyObject *)self->top;
  node->start_ns = start_ns;
  node->offset = self->sf_sz;
  self->sz += 1;
  self->sf_sz += 1;
  node->frame_desp = frame_desp;
  self->current_depth += 1;
  self->top = node;
  Py_DECREF(node);
}

static void TraceProfiler_FinishUnclosedAsyncFrame(TraceProfiler *self) {
  Py_ssize_t children_len = PyList_Size(self->top->succ);
  if (children_len == 0) {
    return;
  }
  FrameNode *last_async_node = pop_last_element(self->top->succ, children_len);
  Py_ssize_t size = PyList_Size(last_async_node->enter_timestamp);
  PyObject *last_element =
      PyList_GetItem(last_async_node->enter_timestamp, size - 1);
  long long last_leave_ns = PyLong_AsLongLong(last_element);

  PyObject *first_element = PyList_GetItem(last_async_node->enter_timestamp, 0);
  long long last_async_start_ns = PyLong_AsLongLong(first_element);
  long long cost_ns = last_leave_ns - last_async_start_ns;

  if (cost_ns >= self->interval) {
    Py_ssize_t pid = self->top->offset;
    PyObject *frame_desp = build_last_async_frame(
        last_async_node->frame_desp, last_async_start_ns, cost_ns, pid);
    Py_ssize_t real_sf_sz = PyList_Size(self->on_sending_frame);
    long long distance = last_async_node->offset + 1 - real_sf_sz;
    long long idx;
    for (idx = 0; idx < distance; idx++) {
      PyList_Append(self->on_sending_frame, Py_None);
    }
    PyList_SetItem(self->on_sending_frame, last_async_node->offset, frame_desp);
  } else {
    self->sf_sz -= 1;
  }
  Py_DECREF(last_async_node);
}

static void
TraceProfiler_FinishUnclosedAsyncFrameWithDepth(TraceProfiler *self) {
  Py_ssize_t children_len = PyList_Size(self->top->succ);
  if (children_len == 0) {
    return;
  }
  FrameNode *last_async_node = pop_last_element(self->top->succ, children_len);
  Py_ssize_t size = PyList_Size(last_async_node->enter_timestamp);
  PyObject *last_element =
      PyList_GetItem(last_async_node->enter_timestamp, size - 1);
  long long last_leave_ns = PyLong_AsLongLong(last_element);

  PyObject *first_element = PyList_GetItem(last_async_node->enter_timestamp, 0);
  long long last_async_start_ns = PyLong_AsLongLong(first_element);
  long long cost_ns = last_leave_ns - last_async_start_ns;

  if (self->current_depth < self->depth_limit) {
    Py_ssize_t pid = self->top->offset;
    PyObject *frame_desp = build_last_async_frame(
        last_async_node->frame_desp, last_async_start_ns, cost_ns, pid);
    Py_ssize_t real_sf_sz = PyList_Size(self->on_sending_frame);
    long long distance = last_async_node->offset + 1 - real_sf_sz;
    long long idx;
    for (idx = 0; idx < distance; idx++) {
      PyList_Append(self->on_sending_frame, Py_None);
    }
    PyList_SetItem(self->on_sending_frame, last_async_node->offset, frame_desp);
  } else {
    self->sf_sz -= 1;
  }
  Py_DECREF(last_async_node);
}

static void TraceProfiler_PushAsyncFrame(TraceProfiler *self,
                                         Py_ssize_t start_ns, PyObject *f_desp,
                                         int is_async_frame,
                                         PyObject *frame_id) {
  if (!is_async_frame) {
    if (self->top->offset == -1) {
      return;
    }
    TraceProfiler_FinishUnclosedAsyncFrame(self);
    TraceProfiler_PushFrame(self, start_ns);
  } else {
    if (self->top->offset == -1) {
      Py_ssize_t children_len = PyList_Size(self->top->succ);
      if (children_len > 0) {
        FrameNode *last_element =
            (FrameNode *)PyList_GetItem(self->top->succ, children_len - 1);
        if (PyObject_RichCompareBool(last_element->frame_id, frame_id, Py_EQ) ==
            1) {
          self->top = last_element;
        } else {
          return;
        }
      } else {
        TraceProfiler_InnerPushAsyncFrame(self, start_ns, f_desp, frame_id);
        return;
      }
    }
    if (PyObject_RichCompareBool(self->top->frame_id, frame_id, Py_EQ) == 1) {
      Py_ssize_t succ_len = PyList_Size(self->top->succ);
      if (succ_len == 0) {
        Py_ssize_t e_size = PyList_Size(self->top->enter_timestamp);
        PyObject *t_last_element =
            PyList_GetItem(self->top->enter_timestamp, e_size - 1);
        long long t_last_leave_ns = PyLong_AsLongLong(t_last_element);
        long long cost_ns = start_ns - t_last_leave_ns;

        if (cost_ns >= self->interval) {
          Py_ssize_t pid = self->top->offset;
          PyObject *frame_desp =
              build_context_switch_frame(t_last_leave_ns, cost_ns, pid);
          Py_ssize_t real_sf_sz = PyList_Size(self->on_sending_frame);
          long long distance = self->sf_sz + 1 - real_sf_sz;
          long long idx;
          for (idx = 0; idx < distance; idx++) {
            PyList_Append(self->on_sending_frame, Py_None);
          }
          PyList_SetItem(self->on_sending_frame, self->sf_sz, frame_desp);
          self->sf_sz += 1;
          Py_DECREF(pop_last_element(self->top->enter_timestamp, e_size));
        }
      } else {
        Py_ssize_t succ_size = PyList_Size(self->top->succ);
        FrameNode *top_succ =
            (FrameNode *)PyList_GetItem(self->top->succ, succ_size - 1);
        self->top = top_succ;
      }
    } else {
      TraceProfiler_FinishUnclosedAsyncFrame(self);
      TraceProfiler_InnerPushAsyncFrame(self, start_ns, f_desp, frame_id);
    }
  }
}

static void TraceProfiler_PushAsyncFrameWithDepth(TraceProfiler *self,
                                                  Py_ssize_t start_ns,
                                                  PyObject *f_desp,
                                                  int is_async_frame,
                                                  PyObject *frame_id) {
  if (!is_async_frame) {
    if (self->top->offset == -1) {
      return;
    }
    TraceProfiler_FinishUnclosedAsyncFrameWithDepth(self);
    TraceProfiler_PushFrameWithDepth(self, start_ns);
  } else {
    if (self->top->offset == -1) {
      Py_ssize_t children_len = PyList_Size(self->top->succ);
      if (children_len > 0) {
        FrameNode *last_element =
            (FrameNode *)PyList_GetItem(self->top->succ, children_len - 1);
        if (PyObject_RichCompareBool(last_element->frame_id, frame_id, Py_EQ) ==
            1) {
          self->top = last_element;
          self->current_depth += 1;
        } else {
          return;
        }
      } else {
        TraceProfiler_InnerPushAsyncFrameWithDepth(self, start_ns, f_desp,
                                                   frame_id);
        return;
      }
    }
    if (PyObject_RichCompareBool(self->top->frame_id, frame_id, Py_EQ) == 1) {
      Py_ssize_t succ_len = PyList_Size(self->top->succ);
      if (succ_len == 0) {
        Py_ssize_t e_size = PyList_Size(self->top->enter_timestamp);
        PyObject *t_last_element =
            PyList_GetItem(self->top->enter_timestamp, e_size - 1);
        long long t_last_leave_ns = PyLong_AsLongLong(t_last_element);
        long long cost_ns = start_ns - t_last_leave_ns;

        if (self->current_depth < self->depth_limit) {
          Py_ssize_t pid = self->top->offset;
          PyObject *frame_desp =
              build_context_switch_frame(t_last_leave_ns, cost_ns, pid);
          Py_ssize_t real_sf_sz = PyList_Size(self->on_sending_frame);
          long long distance = self->sf_sz + 1 - real_sf_sz;
          long long idx;
          for (idx = 0; idx < distance; idx++) {
            PyList_Append(self->on_sending_frame, Py_None);
          }
          PyList_SetItem(self->on_sending_frame, self->sf_sz, frame_desp);
          self->sf_sz += 1;
          Py_DECREF(pop_last_element(self->top->enter_timestamp, e_size));
        }
      } else {
        Py_ssize_t succ_size = PyList_Size(self->top->succ);
        FrameNode *top_succ =
            (FrameNode *)PyList_GetItem(self->top->succ, succ_size - 1);
        self->top = top_succ;
        self->current_depth += 1;
      }
    } else {
      TraceProfiler_FinishUnclosedAsyncFrameWithDepth(self);
      TraceProfiler_InnerPushAsyncFrameWithDepth(self, start_ns, f_desp,
                                                 frame_id);
    }
  }
}

static FrameNode *TraceProfiler_PopFrame(TraceProfiler *self) {
  FrameNode *top_frame = (FrameNode *)self->top;
  self->top = (FrameNode *)top_frame->prev;
  top_frame->prev = NULL;
  self->sz -= 1;
  return top_frame;
}

static FrameNode *TraceProfiler_PopFrameWithDepth(TraceProfiler *self) {
  FrameNode *top_frame = (FrameNode *)self->top;
  self->top = (FrameNode *)top_frame->prev;
  top_frame->prev = NULL;
  self->sz -= 1;
  self->current_depth -= 1;
  return top_frame;
}

static FrameNode *TraceProfiler_PopFrameAsync(TraceProfiler *self,
                                              int is_async_frame,
                                              long long end_time) {
  if (self->top == NULL || self->top->offset == -1) {
    return NULL;
  }
  if (!is_async_frame) {
    FrameNode *top_frame = (FrameNode *)self->top;
    self->top = (FrameNode *)top_frame->prev;
    top_frame->prev = NULL;
    self->sz -= 1;
    return top_frame;
  } else {
    PyObject *e_time_obj = PyLong_FromLong(end_time);
    PyList_Append(self->top->enter_timestamp,
                  e_time_obj); // PyList_Append Increment obj's reference
    Py_DECREF(e_time_obj);

    self->top = (FrameNode *)self->top->prev;
    return NULL;
  }
}

static FrameNode *TraceProfiler_PopFrameAsyncWithDepth(TraceProfiler *self,
                                                       int is_async_frame,
                                                       long long end_time) {
  if (self->top == NULL || self->top->offset == -1) {
    return NULL;
  }
  if (!is_async_frame) {
    FrameNode *top_frame = (FrameNode *)self->top;
    self->top = (FrameNode *)top_frame->prev;
    top_frame->prev = NULL;
    self->sz -= 1;
    self->current_depth -= 1;
    return top_frame;
  } else {
    PyObject *e_time_obj = PyLong_FromLong(end_time);
    PyList_Append(self->top->enter_timestamp,
                  e_time_obj); // PyList_Append Increment obj's reference
    Py_DECREF(e_time_obj);

    self->current_depth -= 1;
    self->top = (FrameNode *)self->top->prev;
    return NULL;
  }
}

static void TraceProfiler_FulfillAsyncUnfinishedRequests(TraceProfiler *self) {
  while (self->top != NULL) {
    if (self->top->offset == -1) {
      Py_ssize_t succ_len = PyList_Size(self->top->succ);
      if (succ_len > 0) {
        FrameNode *cur_top = self->top;
        self->top = pop_last_element(self->top->succ, succ_len);
        Py_DECREF(cur_top);
      } else {
        return;
      }
    } else {
      FrameNode *last_async_node = self->top;
      Py_ssize_t size = PyList_Size(last_async_node->enter_timestamp);
      PyObject *last_element =
          PyList_GetItem(last_async_node->enter_timestamp, size - 1);
      long long last_leave_ns = PyLong_AsLongLong(last_element);

      PyObject *first_element =
          PyList_GetItem(last_async_node->enter_timestamp, 0);
      long long last_async_start_ns = PyLong_AsLongLong(first_element);
      long long cost_ns = last_leave_ns - last_async_start_ns;

      if (cost_ns >= self->interval) {
        FrameNode *prev_node = (FrameNode *)self->top->prev;
        Py_ssize_t pid = prev_node->offset;
        PyObject *frame_desp = build_last_async_frame(
            last_async_node->frame_desp, last_async_start_ns, cost_ns, pid);
        Py_ssize_t real_sf_sz = PyList_Size(self->on_sending_frame);
        long long distance = last_async_node->offset + 1 - real_sf_sz;
        long long idx;
        for (idx = 0; idx < distance; idx++) {
          PyList_Append(self->on_sending_frame, Py_None);
        }
        PyList_SetItem(self->on_sending_frame, last_async_node->offset,
                       frame_desp);
        Py_ssize_t succ_len_2 = PyList_Size(self->top->succ);
        if (succ_len_2 > 0) {
          FrameNode *cur_top_2 = self->top;
          self->top = pop_last_element(self->top->succ, succ_len_2);
          Py_DECREF(cur_top_2);
        } else {
          return;
        }
      } else {
        return;
      }
    }
  }
}

static void
TraceProfiler_FulfillAsyncUnfinishedRequestsWithDepth(TraceProfiler *self) {
  while (self->top != NULL) {
    if (self->top->offset == -1) {
      Py_ssize_t succ_len = PyList_Size(self->top->succ);
      if (succ_len > 0) {
        FrameNode *cur_top = self->top;
        self->top = pop_last_element(self->top->succ, succ_len);
        self->current_depth += 1;
        Py_DECREF(cur_top);
      } else {
        return;
      }
    } else {
      FrameNode *last_async_node = self->top;
      Py_ssize_t size = PyList_Size(last_async_node->enter_timestamp);
      PyObject *last_element =
          PyList_GetItem(last_async_node->enter_timestamp, size - 1);
      long long last_leave_ns = PyLong_AsLongLong(last_element);

      PyObject *first_element =
          PyList_GetItem(last_async_node->enter_timestamp, 0);
      long long last_async_start_ns = PyLong_AsLongLong(first_element);
      long long cost_ns = last_leave_ns - last_async_start_ns;

      if (self->current_depth <= self->depth_limit) {
        FrameNode *prev_node = (FrameNode *)self->top->prev;
        Py_ssize_t pid = prev_node->offset;
        PyObject *frame_desp = build_last_async_frame(
            last_async_node->frame_desp, last_async_start_ns, cost_ns, pid);
        Py_ssize_t real_sf_sz = PyList_Size(self->on_sending_frame);
        long long distance = last_async_node->offset + 1 - real_sf_sz;
        long long idx;
        for (idx = 0; idx < distance; idx++) {
          PyList_Append(self->on_sending_frame, Py_None);
        }
        PyList_SetItem(self->on_sending_frame, last_async_node->offset,
                       frame_desp);
        Py_ssize_t succ_len_2 = PyList_Size(self->top->succ);
        if (succ_len_2 > 0) {
          FrameNode *cur_top_2 = self->top;
          self->top = pop_last_element(self->top->succ, succ_len_2);
          self->current_depth += 1;
          Py_DECREF(cur_top_2);
        } else {
          return;
        }
      } else {
        return;
      }
    }
  }
}

static TraceProfiler *TraceProfiler_New(long long interval, Py_ssize_t is_async,
                                        Py_ssize_t depth_limit) {
  TraceProfiler *trace_profiler =
      PyObject_New(TraceProfiler, &TraceProfiler_Type);
  trace_profiler->target = NULL;
  trace_profiler->interval = interval;
  trace_profiler->is_async = is_async;
  FrameNode *node = FrameNode_New();
  node->offset = -1;
  trace_profiler->top = (FrameNode *)node;
  trace_profiler->sf_sz = 0;
  trace_profiler->current_depth = 0;
  trace_profiler->depth_limit = depth_limit;

  trace_profiler->sz = 1;
  trace_profiler->on_sending_frame = PyList_New(0);
  trace_profiler->out_queue = NULL;
  return trace_profiler;
}

static void TraceProfiler_SendTraceFrames(TraceProfiler *self) {
  if (self->is_async) {
    if (self->depth_limit <= 0) {
      TraceProfiler_FulfillAsyncUnfinishedRequests(self);
    } else {
      TraceProfiler_FulfillAsyncUnfinishedRequestsWithDepth(self);
    }
  }

#if PY_VERSION_HEX >= 0x03090000
  // vectorcall implementation could be faster, is available in Python 3.9
  PyObject *callargs[3] = {NULL, (PyObject *)self->out_queue,
                           (PyObject *)self->on_sending_frame};
  PyObject *result = PyObject_Vectorcall(
      self->target, callargs + 1, 2 | PY_VECTORCALL_ARGUMENTS_OFFSET, NULL);
#else
  PyObject *result = PyObject_CallFunctionObjArgs(self->target, self->out_queue,
                                                  self->on_sending_frame, NULL);
#endif
  Py_XDECREF(result);
}

//////////////////////
// Public functions //
//////////////////////

/**
 * called when python/c method are called.
 */
static int profile(PyObject *op, PyFrameObject *frame, int what,
                   PyObject *arg) {
  TraceProfiler *tp = (TraceProfiler *)op;
  PyObject *result;

  long long current_time = _get_time_ns();
  // what:        0         1           3        4           5             6
  // return:      call   exception    return    c_call    c_exception   c_return
  if (what == 0 || what == 4) {
    // call/c_call
    TraceProfiler_PushFrame(tp, current_time);
  } else if (what == 3 || what == 6 || what == 5) {
    // return/c_exception/c_return
    FrameNode *node = TraceProfiler_PopFrame(tp);
    long long cost_ns = current_time - node->start_ns;
    if (cost_ns < tp->interval) {
      tp->sf_sz -= 1;
    } else {
      int c_frame = (what == 3) ? 0 : 1;
      FrameNode *parent_node = (FrameNode *)tp->top;
      PyObject *frame_desp = _get_frame_info(frame, node->start_ns, cost_ns,
                                             parent_node->offset, arg, c_frame);

      Py_ssize_t real_sf_sz = PyList_Size(tp->on_sending_frame);
      long long distance = node->offset + 1 - real_sf_sz;
      long long idx;
      for (idx = 0; idx < distance; idx++) {
        PyList_Append(tp->on_sending_frame, Py_None);
      }
      PyList_SetItem(tp->on_sending_frame, node->offset, frame_desp);
    }
    Py_DECREF(node);
  }
  return 0;
}

static int profile_with_depth(PyObject *op, PyFrameObject *frame, int what,
                              PyObject *arg) {
  TraceProfiler *tp = (TraceProfiler *)op;
  PyObject *result;

  long long current_time = _get_time_ns();
  // what:        0         1           3        4           5             6
  // return:      call   exception    return    c_call    c_exception   c_return
  if (what == 0 || what == 4) {
    // call/c_call
    TraceProfiler_PushFrameWithDepth(tp, current_time);
  } else if (what == 3 || what == 6 || what == 5) {
    // return/c_exception/c_return
    FrameNode *node = TraceProfiler_PopFrameWithDepth(tp);
    long long cost_ns = current_time - node->start_ns;
    if (tp->current_depth >= tp->depth_limit) {
      tp->sf_sz -= 1;
    } else {
      int c_frame = (what == 3) ? 0 : 1;
      FrameNode *parent_node = (FrameNode *)tp->top;
      PyObject *frame_desp = _get_frame_info(frame, node->start_ns, cost_ns,
                                             parent_node->offset, arg, c_frame);

      Py_ssize_t real_sf_sz = PyList_Size(tp->on_sending_frame);
      long long distance = node->offset + 1 - real_sf_sz;
      long long idx;
      for (idx = 0; idx < distance; idx++) {
        PyList_Append(tp->on_sending_frame, Py_None);
      }
      PyList_SetItem(tp->on_sending_frame, node->offset, frame_desp);
    }
    Py_DECREF(node);
  }
  return 0;
}

static int async_profile(PyObject *op, PyFrameObject *frame, int what,
                         PyObject *arg) {
  TraceProfiler *tp = (TraceProfiler *)op;
  PyObject *result;

  long long current_time = _get_time_ns();
  // what:        0         1           3        4           5             6
  // return:      call   exception    return    c_call    c_exception   c_return
  PyCodeObject *code_obj = _code_from_frame(frame);
  int is_async_frame = (code_obj->co_flags & 0x80) > 0 && (what < 4);
  Py_DECREF(code_obj);
  if (what == 0 || what == 4) {
    // call/c_call
    int c_frame = (what == 4) ? 1 : 0;
    TraceProfiler_PushAsyncFrame(
        tp, current_time, _get_header(frame, c_frame, arg), is_async_frame,
        PyLong_FromVoidPtr((void *)frame));
  } else if (what == 3 || what == 6 || what == 5) {
    // return/c_exception/c_return
    FrameNode *node =
        TraceProfiler_PopFrameAsync(tp, is_async_frame, current_time);
    if (!is_async_frame && node != NULL) {
      long long cost_ns = current_time - node->start_ns;
      if (cost_ns < tp->interval) {
        tp->sf_sz -= 1;
      } else {
        int c_frame = (what == 3) ? 0 : 1;
        FrameNode *parent_node = (FrameNode *)tp->top;
        PyObject *frame_desp = _get_frame_info(
            frame, node->start_ns, cost_ns, parent_node->offset, arg, c_frame);

        Py_ssize_t real_sf_sz = PyList_Size(tp->on_sending_frame);
        long long distance = node->offset + 1 - real_sf_sz;
        long long idx;
        for (idx = 0; idx < distance; idx++) {
          PyList_Append(tp->on_sending_frame, Py_None);
        }
        PyList_SetItem(tp->on_sending_frame, node->offset, frame_desp);
      }
    }
    Py_XDECREF(node);
  }
  return 0;
}

static int async_profile_with_depth(PyObject *op, PyFrameObject *frame,
                                    int what, PyObject *arg) {
  TraceProfiler *tp = (TraceProfiler *)op;
  PyObject *result;

  long long current_time = _get_time_ns();
  // what:        0         1           3        4           5             6
  // return:      call   exception    return    c_call    c_exception   c_return
  PyCodeObject *code_obj = _code_from_frame(frame);
  int is_async_frame = (code_obj->co_flags & 0x80) > 0 && (what < 4);
  Py_DECREF(code_obj);
  if (what == 0 || what == 4) {
    // call/c_call
    int c_frame = (what == 4) ? 1 : 0;
    TraceProfiler_PushAsyncFrameWithDepth(
        tp, current_time, _get_header(frame, c_frame, arg), is_async_frame,
        PyLong_FromVoidPtr((void *)frame));
  } else if (what == 3 || what == 6 || what == 5) {
    // return/c_exception/c_return
    FrameNode *node =
        TraceProfiler_PopFrameAsyncWithDepth(tp, is_async_frame, current_time);
    if (!is_async_frame && node != NULL) {
      long long cost_ns = current_time - node->start_ns;
      if (tp->current_depth >= tp->depth_limit) {
        tp->sf_sz -= 1;
      } else {
        int c_frame = (what == 3) ? 0 : 1;
        FrameNode *parent_node = (FrameNode *)tp->top;
        PyObject *frame_desp = _get_frame_info(
            frame, node->start_ns, cost_ns, parent_node->offset, arg, c_frame);

        Py_ssize_t real_sf_sz = PyList_Size(tp->on_sending_frame);
        long long distance = node->offset + 1 - real_sf_sz;
        long long idx;
        for (idx = 0; idx < distance; idx++) {
          PyList_Append(tp->on_sending_frame, Py_None);
        }
        PyList_SetItem(tp->on_sending_frame, node->offset, frame_desp);
      }
    }
    Py_XDECREF(node);
  }
  return 0;
}

static PyObject *set_trace_profile(PyObject *m, PyObject *args,
                                   PyObject *kwds) {

  TraceProfiler *profiler = NULL;
  PyObject *out_q;
  PyObject *target;
  long long interval = 0;
  Py_ssize_t depth_limit = 0;
  int async_func = 0;

  if (!PyArg_ParseTuple(args, "OOLpn", &target, &out_q, &interval, &async_func,
                        &depth_limit)) {
    return NULL;
  }
  if (out_q == NULL) {
    return NULL;
  }

  profiler = TraceProfiler_New(interval, async_func, depth_limit);
  Py_XINCREF(out_q);
  profiler->out_queue = out_q;
  Py_XINCREF(target);
  profiler->target = target;
  if (async_func == 1) {
    if (depth_limit <= 0) {
      PyEval_SetProfile(async_profile, (PyObject *)profiler);
    } else {
      PyEval_SetProfile(async_profile_with_depth, (PyObject *)profiler);
    }
  } else {
    if (depth_limit <= 0) {
      PyEval_SetProfile(profile, (PyObject *)profiler);
    } else {
      PyEval_SetProfile(profile_with_depth, (PyObject *)profiler);
    }
  }
  return (PyObject *)profiler;
}

static PyObject *remove_trace_profile(PyObject *m, PyObject *args,
                                      PyObject *kwds) {
  PyEval_SetProfile(NULL, NULL);
  PyObject *profiler_obj;

  if (!PyArg_ParseTuple(args, "O", &profiler_obj)) {
    Py_RETURN_NONE;
  }
  if (profiler_obj == Py_None || profiler_obj == NULL) {
    Py_RETURN_NONE;
  }
  TraceProfiler *profiler = (TraceProfiler *)profiler_obj;
  TraceProfiler_SendTraceFrames(profiler);
  Py_RETURN_NONE;
}

///////////////////////////
// Module initialization //
///////////////////////////

static PyMethodDef module_methods[] = {
    {"set_trace_profile", (PyCFunction)set_trace_profile,
     METH_VARARGS | METH_KEYWORDS, "set_trace_profile implementation."},
    {"remove_trace_profile", (PyCFunction)remove_trace_profile,
     METH_VARARGS | METH_KEYWORDS, "remove by setting sys.setprofile(None)"},
    {NULL} /* Sentinel */
};

PyMODINIT_FUNC PyInit_trace_profile_C(void) {
  static struct PyModuleDef moduledef = {
      PyModuleDef_HEAD_INIT, "trace_profile_C", "PyFlight trace supports.", -1,
      module_methods};
  return PyModule_Create(&moduledef);
}
