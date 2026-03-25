#ifndef PROCESS_UTILS_H
#define PROCESS_UTILS_H

#include <dirent.h>
#include <dlfcn.h>
#include <limits.h>
#include <string>
#include <unistd.h>

#ifdef ARM
#define REG_TYPE struct user_regs
#else
#define REG_TYPE struct user_regs_struct
#endif

/**
 * @brief A utility class for process-related operations
 *
 * This class provides static methods for finding processes, managing memory,
 * handling libraries, and working with instructions in the context of process
 * injection.
 */
class ProcessUtils {
public:
  // Memory management
  /**
   * @brief Find a free memory address in the target process
   * @param process_id PID of the target process
   * @return Address of free memory, or 0 on failure
   */
  static long findFreeMemoryAddress(pid_t process_id);

  /**
   * @brief Get the base address of libc in the target process
   * @param process_id PID of the target process
   * @return Base address of libc, or 0 on failure
   */
  static long getLibcBaseAddress(pid_t process_id);

  // Library management
  /**
   * @brief Check if a library is loaded in the target process
   * @param process_id PID of the target process
   * @param library_name Name of the library to check
   * @return true if the library is loaded, false otherwise
   */
  static bool isLibraryLoaded(pid_t process_id,
                              const std::string &library_name);

  /**
   * @brief Resolve the address of a function in the current process
   * @param function_name Name of the function to resolve
   * @return Address of the function, or 0 on failure
   */
  static long resolveFunctionAddress(const std::string &function_name);

  // Instruction management
  /**
   * @brief Locate the return instruction in a function
   * @param end_address End address of the function
   * @return Pointer to the return instruction
   */
  static unsigned char *locateReturnInstruction(void *end_address);
};

#endif // PROCESS_UTILS_H
