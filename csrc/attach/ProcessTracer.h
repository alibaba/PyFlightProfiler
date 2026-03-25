#ifndef PROCESS_TRACER_H
#define PROCESS_TRACER_H

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <signal.h>
#include <sys/ptrace.h>
#include <sys/user.h>
#include <sys/wait.h>
#include <unistd.h>

#ifdef ARM
#define REG_TYPE struct user_regs
#else
#define REG_TYPE struct user_regs_struct
#endif

/**
 * @brief A class for tracing and manipulating a process using ptrace
 *
 * This class provides functionality to attach to a process, manipulate its
 * registers and memory, and control its execution.
 */
class ProcessTracer {
public:
  /**
   * @brief Constructor for ProcessTracer
   * @param process_id PID of the process to trace
   * @param debug_mode Enable debug logging
   */
  ProcessTracer(pid_t process_id, bool debug_mode = false);

  /**
   * @brief Destructor for ProcessTracer
   *
   * Automatically detaches from the process if still attached.
   */
  ~ProcessTracer();

  // Process attachment and detachment
  /**
   * @brief Attach to the target process
   * @return true if attachment was successful, false otherwise
   */
  bool attach();

  /**
   * @brief Detach from the target process
   * @return true if detachment was successful, false otherwise
   */
  bool detach();

  // Process execution control
  /**
   * @brief Continue execution of the target process
   * @return true if continue was successful, false otherwise
   */
  bool continueExecution();

  /**
   * @brief Stop the target process
   */
  void stop();

  // Register operations
  /**
   * @brief Get the current register state of the target process
   * @param registers Pointer to store the register state
   * @return true if registers were successfully retrieved, false otherwise
   */
  bool getRegisters(REG_TYPE *registers);

  /**
   * @brief Set the register state of the target process
   * @param registers Pointer to the register state to set
   * @return true if registers were successfully set, false otherwise
   */
  bool setRegisters(REG_TYPE *registers);

  // Memory operations
  /**
   * @brief Read memory from the target process
   * @param address Address to read from
   * @param buffer Buffer to store the read data
   * @param length Number of bytes to read
   * @return true if memory was successfully read, false otherwise
   */
  bool readMemory(unsigned long address, void *buffer, int length);

  /**
   * @brief Write memory to the target process
   * @param address Address to write to
   * @param buffer Buffer containing the data to write
   * @param length Number of bytes to write
   * @return true if memory was successfully written, false otherwise
   */
  bool writeMemory(unsigned long address, const void *buffer, int length);

  // Signal handling
  /**
   * @brief Get signal information for the target process
   * @return siginfo_t structure containing signal information
   */
  siginfo_t getSignalInfo();

  /**
   * @brief Verify the signal status of the target process
   * @return true if signal status is as expected, false otherwise
   */
  bool verifySignalStatus();

  // Failure recovery
  /**
   * @brief Restore the process state after a failed attach attempt
   * @param attach_address Address where the shellcode was loaded
   * @param backup_data Pointer to the original data at the attach address
   * @param data_length Length of the backup data
   * @param registers Pointer to the original register state
   * @return true if restoration was successful, false otherwise
   */
  bool recoverAttach(long attach_address, const void *backup_data,
                     size_t data_length, REG_TYPE *registers);

  // Accessor for debug mode
  /**
   * @brief Get the debug mode flag
   * @return true if debug mode is enabled, false otherwise
   */
  bool isDebugMode() const { return debug_mode_; }

private:
  pid_t process_id_; ///< PID of the process being traced
  bool is_attached_; ///< Flag indicating if we're currently attached to the
                     ///< process
  bool debug_mode_;  ///< Flag indicating if debug logging is enabled

  // Helper functions
  /**
   * @brief Sleep for a specified number of milliseconds
   * @param milliseconds Number of milliseconds to sleep
   */
  void sleepMs(int milliseconds);
};

#endif // PROCESS_TRACER_H
