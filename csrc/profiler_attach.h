

#ifndef __PROFILER_ATTACH_H__
#define __PROFILER_ATTACH_H__

#ifdef __cplusplus
extern "C" {
#endif

int profiler_attach(char *fn, int p, unsigned long nm_symbol_offset);

#ifdef __cplusplus
}
#endif

#endif
