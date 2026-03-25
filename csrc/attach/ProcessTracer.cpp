#include "ProcessTracer.h"
#include <errno.h>
#include <iostream>
#include <sstream>
#include <time.h>

/**
 * @brief Macro to check ptrace operation results and handle errors
 *
 * This macro checks if a ptrace operation failed and prints an error message
 * before returning false.
 *
 * @param result Result of the ptrace operation
 * @param operation Name of the ptrace operation for error reporting
 */
#define CHECK_PTRACE_RESULT(result, operation)                                 \
  do {                                                                         \
    if ((result) == -1) {                                                      \
      if (debug_mode_) {                                                       \
        std::cerr << "[ERROR] PyFlightProfiler: ptrace(" << #operation         \
                  << ") failed: " << strerror(errno) << std::endl;             \
      }                                                                        \
      return false;                                                            \
    }                                                                          \
  } while (0)

/**
 * @brief Constructor for ProcessTracer
 *
 * Initializes the ProcessTracer with the target process ID and sets the
 * attachment flag to false.
 *
 * @param process_id PID of the process to trace
 */
ProcessTracer::ProcessTracer(pid_t process_id, bool debug_mode)
    : process_id_(process_id), is_attached_(false), debug_mode_(debug_mode) {}

/**
 * @brief Destructor for ProcessTracer
 *
 * Automatically detaches from the process if still attached.
 */
ProcessTracer::~ProcessTracer() {
  if (is_attached_) {
    detach();
  }
}

/**
 * @brief Attach to the target process
 *
 * Uses ptrace to attach to the target process and waits for it to stop.
 *
 * @return true if attachment was successful, false otherwise
 */
bool ProcessTracer::attach() {
  int result = ptrace(PTRACE_ATTACH, process_id_, NULL, NULL);
  CHECK_PTRACE_RESULT(result, PTRACE_ATTACH);

  int wait_status;
  if (waitpid(process_id_, &wait_status, WUNTRACED) != process_id_) {
    if (debug_mode_) {
      std::cerr << "waitpid(" << process_id_ << ") failed: " << strerror(errno)
                << std::endl;
    }
    return false;
  }

  is_attached_ = true;
  return true;
}

/**
 * @brief Detach from the target process
 *
 * Uses ptrace to detach from the target process.
 *
 * @return true if detachment was successful, false otherwise
 */
bool ProcessTracer::detach() {
  int result = ptrace(PTRACE_DETACH, process_id_, NULL, NULL);
  CHECK_PTRACE_RESULT(result, PTRACE_DETACH);
  is_attached_ = false;
  return true;
}

/**
 * @brief Continue execution of the target process
 *
 * Uses ptrace to continue execution of the target process and verifies
 * that it stops with the expected signal.
 *
 * @return true if continue was successful, false otherwise
 */
bool ProcessTracer::continueExecution() {
  int result = ptrace(PTRACE_CONT, process_id_, NULL, NULL);
  CHECK_PTRACE_RESULT(result, PTRACE_CONT);

  // Wait for the target process to stop (e.g., hit INT3 breakpoint)
  int wait_status;
  pid_t waited_pid = waitpid(process_id_, &wait_status, 0);
  if (waited_pid != process_id_) {
    if (debug_mode_) {
      std::cerr << "[ERROR] PyFlightProfiler: waitpid(" << process_id_
                << ") failed or returned unexpected pid " << waited_pid << ": "
                << strerror(errno) << std::endl;
    }
    return false;
  }

  // Check if the process stopped (not exited or terminated)
  if (!WIFSTOPPED(wait_status)) {
    if (debug_mode_) {
      std::cerr << "[ERROR] PyFlightProfiler: process " << process_id_
                << " did not stop as expected, wait_status=" << wait_status
                << std::endl;
    }
    return false;
  }

  // Make sure the target process received SIGTRAP after stopping.
  return verifySignalStatus();
}

/**
 * @brief Stop the target process
 *
 * Sends a SIGSTOP signal to the target process and exits the current process.
 */
void ProcessTracer::stop() {
  ptrace(PTRACE_CONT, process_id_, NULL, SIGSTOP);
  exit(1);
}

/**
 * @brief Get the current register state of the target process
 *
 * Uses ptrace to retrieve the current register state of the target process.
 *
 * @param registers Pointer to store the register state
 * @return true if registers were successfully retrieved, false otherwise
 */
bool ProcessTracer::getRegisters(REG_TYPE *registers) {
  int result = ptrace(PTRACE_GETREGS, process_id_, NULL, registers);
  CHECK_PTRACE_RESULT(result, PTRACE_GETREGS);
  return true;
}

/**
 * @brief Set the register state of the target process
 *
 * Uses ptrace to set the register state of the target process.
 *
 * @param registers Pointer to the register state to set
 * @return true if registers were successfully set, false otherwise
 */
bool ProcessTracer::setRegisters(REG_TYPE *registers) {
  int result = ptrace(PTRACE_SETREGS, process_id_, NULL, registers);
  CHECK_PTRACE_RESULT(result, PTRACE_SETREGS);
  return true;
}

/**
 * @brief Read memory from the target process
 *
 * Uses ptrace to read memory from the target process in word-sized chunks.
 *
 * @param address Address to read from
 * @param buffer Buffer to store the read data
 * @param length Number of bytes to read
 * @return true if memory was successfully read, false otherwise
 */
bool ProcessTracer::readMemory(unsigned long address, void *buffer,
                               int length) {
  int bytes_read = 0;
  int i = 0;
  long word = 0;
  long *ptr = static_cast<long *>(buffer);

  while (bytes_read < length) {
    word = ptrace(PTRACE_PEEKTEXT, process_id_, address + bytes_read, NULL);
    CHECK_PTRACE_RESULT(word, PTRACE_PEEKTEXT);
    bytes_read += sizeof(word);
    ptr[i++] = word;
  }

  return true;
}

/**
 * @brief Write memory to the target process
 *
 * Uses ptrace to write memory to the target process in word-sized chunks.
 *
 * @param address Address to write to
 * @param buffer Buffer containing the data to write
 * @param length Number of bytes to write
 * @return true if memory was successfully written, false otherwise
 */
bool ProcessTracer::writeMemory(unsigned long address, const void *buffer,
                                int length) {
  int byte_count = 0;
  long word = 0;

  while (byte_count < length) {
    memcpy(&word, static_cast<const char *>(buffer) + byte_count, sizeof(word));
    int result =
        ptrace(PTRACE_POKETEXT, process_id_, address + byte_count, word);
    CHECK_PTRACE_RESULT(result, PTRACE_POKETEXT);
    byte_count += sizeof(word);
  }

  return true;
}

/**
 * @brief Get signal information for the target process
 *
 * Retrieves signal information for the target process, with retry logic
 * to handle cases where the process may not have reached the expected
 * interruption point yet.
 *
 * @return siginfo_t structure containing signal information
 */
siginfo_t ProcessTracer::getSignalInfo() {
  siginfo_t signal_info;
  // With waitpid() in continueExecution(), the process should already be
  // stopped. Retry a few times just in case, but much shorter timeout is
  // needed.
  for (int i = 0; i < 10; i++) {
    if (ptrace(PTRACE_GETSIGINFO, process_id_, NULL, &signal_info) != -1) {
      return signal_info;
    }
    sleepMs(1);
  }

  // this is mostly due to gil lock not released, so injected code cannot
  // execute
  signal_info.si_signo = -1;
  return signal_info;
}

/**
 * @brief Verify the signal status of the target process
 *
 * Checks that the target process stopped with the expected SIGTRAP signal.
 * If not, it prints an error message and stops the process for debugging.
 *
 * @return true if signal status is as expected, false otherwise
 */
bool ProcessTracer::verifySignalStatus() {
  // Check the signal that the child stopped with.
  siginfo_t signal_info = getSignalInfo();
  if (signal_info.si_signo == -1) {
    return false;
  }

  // If it wasn't SIGTRAP, then something bad happened (most likely a segfault).
  if (signal_info.si_signo != SIGTRAP) {
    if (debug_mode_) {
      std::cerr << "instead of expected SIGTRAP, target stopped with signal "
                << signal_info.si_signo << ": "
                << strsignal(signal_info.si_signo) << std::endl;
      std::cerr << "sending process " << process_id_
                << " a SIGSTOP signal for debugging purposes" << std::endl;
    }
    ptrace(PTRACE_CONT, process_id_, NULL, SIGSTOP);
    exit(1);
  }

  return true;
}

/**
 * @brief Restore the process state after a failed attach attempt
 *
 * This function performs the three required steps to restore the process state:
 * 1. Write the original memory data back to the attach address
 * 2. Restore the original register state
 * 3. Detach from the process
 *
 * @param attach_address Address where the shellcode was loaded
 * @param backup_data Pointer to the original data at the attach address
 * @param data_length Length of the backup data
 * @param registers Pointer to the original register state
 * @return true if restoration was successful, false otherwise
 */
bool ProcessTracer::recoverAttach(long attach_address, const void *backup_data,
                                  size_t data_length, REG_TYPE *registers) {
  // Step 1: Write the original memory data back to the attach address
  if (!writeMemory(attach_address, backup_data, data_length)) {
    if (debug_mode_) {
      std::cerr << "[ERROR] PyFlightProfiler: Failed to recover original "
                   "memory data at address 0x"
                << std::hex << attach_address << std::dec << std::endl;
    }
    return false;
  }

  // Step 2: Restore the original register state
  if (!setRegisters(registers)) {
    if (debug_mode_) {
      std::cerr << "[ERROR] PyFlightProfiler: Failed to restore original "
                   "register state."
                << std::endl;
    }
    return false;
  }

  // Step 3: Detach from the process
  if (!detach()) {
    if (debug_mode_) {
      std::cerr << "[ERROR] PyFlightProfiler: Failed to detach from process "
                << process_id_ << std::endl;
    }
    return false;
  }
  return true;
}

/**
 * @brief Sleep for a specified number of milliseconds
 *
 * Uses nanosleep to sleep for the specified number of milliseconds.
 *
 * @param milliseconds Number of milliseconds to sleep
 */
void ProcessTracer::sleepMs(int milliseconds) {
  struct timespec sleep_time;
  sleep_time.tv_sec = 0;
  sleep_time.tv_nsec = milliseconds * 1000000; // Convert to nanoseconds
  nanosleep(&sleep_time, NULL);
}
