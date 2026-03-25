IS_DARWIN := $(shell uname -s | grep Darwin)
ARCH := $(shell uname -m|sed 's/aarch64/arm64/g')
OS := $(if $(IS_DARWIN),macos,linux)
SHARED_LIB_SUFFIX := $(if $(IS_DARWIN),dylib,so)
FRIDA_GUM_DEVKIT := $(shell echo "frida-gum-devkit-16.5.1-${OS}-${ARCH}.tar.xz")
BASE_DIR := $(shell pwd)
PY_HEADER_PATH := $(shell sh flight_profiler/shell/py_header_locate.sh)
SUDO_CMD := $(shell if [ "$$(uname -s)" = "Darwin" ] && python3 -c "import sys; exit(0 if sys.version_info >= (3, 14) else 1)"; then echo "sudo"; fi)

INJECT_CC := gcc
INJECT_CFLAGS := -std=c++11
CC := g++
CFLAGS := $(if $(IS_DARWIN),-dynamiclib,-shared) -fPIC -std=c++11
LDFLAGS := $(if $(IS_DARWIN),-lm -undefined dynamic_lookup,)

all: build

build: flight_profiler_agent.${SHARED_LIB_SUFFIX} scripts
	@poetry build --format wheel

flight_profiler_agent.${SHARED_LIB_SUFFIX}:
	@echo "found python header dir:${PY_HEADER_PATH}"
	@mkdir -p build/lib
	@mkdir -p build/include
	@mkdir -p flight_profiler/lib
	@echo "download frida lib ${FRIDA_GUM_DEVKIT}"
	@wget "https://github.com/frida/frida/releases/download/16.5.1/${FRIDA_GUM_DEVKIT}" -O build/${FRIDA_GUM_DEVKIT}
	@tar -xf build/${FRIDA_GUM_DEVKIT} -C build/
	@mv build/frida-gum.h build/include/
	@mv build/libfrida-gum.* build/lib/
	@echo "compiling flight_profiler_agent.${SHARED_LIB_SUFFIX}"
	@${CC} ${CFLAGS} ${LDFLAGS} -I${PY_HEADER_PATH} -Ibuild/include -Icsrc \
	csrc/profiler_attach.cpp csrc/frida_profiler.cpp \
	csrc/time_util.cpp csrc/symbol_util.cpp csrc/python_util.cpp \
    csrc/py_gil_intercept.cpp csrc/py_gil_stat.cpp csrc/stack/py_stack.cpp \
	-o build/lib/flight_profiler_agent.${SHARED_LIB_SUFFIX} -Lbuild/lib -lfrida-gum  -ldl
	@if [ "$(IS_DARWIN)" != "Darwin" ]; then \
        $(CC) $(INJECT_CFLAGS) -Icsrc/attach/ -o build/lib/attach csrc/attach/ProcessTracer.cpp csrc/attach/ProcessUtils.cpp csrc/attach/AttachAgent.cpp csrc/attach/attach.cpp -ldl;\
        cp build/lib/attach flight_profiler/lib/attach;\
    fi
	@cp build/lib/flight_profiler_agent.${SHARED_LIB_SUFFIX} flight_profiler/lib/flight_profiler_agent.${SHARED_LIB_SUFFIX}

scripts:
	@chmod 755 ${BASE_DIR}/flight_profiler/shell/*

test: install
	@echo "poetry test"
	@export PYTHONPATH=${BASE_DIR}:$PYTHONPATH
	@$(SUDO_CMD) pytest ${BASE_DIR}/flight_profiler/test

install: clean build
	@echo "poetry install"
	@pip3 uninstall -y flight_profiler || true
	@pip3 install dist/`ls dist |grep ".whl"`
	@unzip dist/`ls dist | grep ".whl"` -d dist/
	@cp dist/flight_profiler/ext/*.so ${BASE_DIR}/flight_profiler/ext
	@rm -rf dist/*[^.whl]

clean:
	@echo "clean build cache"
	@rm -rf build
	@rm -rf flight_profiler/lib
	@rm -rf flight_profiler/ext/*.so
	@rm -rf dist
	@rm -rf setup.py
