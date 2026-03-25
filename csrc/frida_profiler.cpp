#include "frida_profiler.h"
#include <assert.h>
static pthread_mutex_t mutex;
static int inited = 0;

// so init
__attribute__((constructor)) static void frida_profiler_init() {
  pthread_mutex_init(&mutex, NULL);
}

#ifdef __cplusplus
extern "C" {
#endif

int init_frida_gum() {
  pthread_mutex_lock(&mutex);
  if (inited != 0) {
    pthread_mutex_unlock(&mutex);
    return 0;
  }
  gum_init_embedded();
  inited = 1;
  pthread_mutex_unlock(&mutex);
  fprintf(stdout, "[PyFlightProfiler] Native profiler initialized.\n");
  return 0;
}

int deinit_frida_gum() {
  pthread_mutex_lock(&mutex);
  if (inited != 1) {
    // pthread_mutex_unlock(&mutex);
    return 0;
  }
  gum_deinit_embedded();
  inited = 0;
  pthread_mutex_unlock(&mutex);
  fprintf(stdout, "[PyFlightProfiler] Native profiler deinitialized.\n");
  return 0;
}

#ifdef __cplusplus
}
#endif
