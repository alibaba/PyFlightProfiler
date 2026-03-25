#include "LibraryInjector.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <limits.h>
#include <memory>
#include <unistd.h>

// Assembly code for injecting shared library
// This is kept as a C function because it needs to be position-independent
extern "C" {
/**
 * @brief Injects a shared library into a target process using assembly code
 *
 * This function performs the following steps:
 * 1. Saves addresses of free() and __libc_dlopen_mode() on the stack
 * 2. Calls malloc() to allocate memory in the target process
 * 3. Calls __libc_dlopen_mode() to load the shared library
 * 4. Calls free() to free the allocated buffer
 *
 * @param malloc_function_address Address of malloc function in target process
 * @param free_function_address Address of free function in target process
 * @param dlopen_function_address Address of dlopen function in target process
 */
void inject_shared_library(long malloc_function_address,
                           long free_function_address,
                           long dlopen_function_address,
                           long library_path_length);

/**
 * @brief Marks the end of inject_shared_library function for size calculation
 */
void inject_shared_library_end();
}

/**
 * @brief Injects a shared library into a target process using optimized
 * assembly code
 *
 * This function performs the following steps:
 * 1. Saves addresses of free() and __libc_dlopen_mode() on the stack
 * 2. Calls malloc() to allocate memory in the target process (ignoring result)
 * 3. Calls __libc_dlopen_mode() to load the shared library
 * 4. Calls free() to free the allocated buffer
 *
 * Optimized to use only 2 interrupts instead of 3 and ignore malloc result.
 *
 * @param malloc_addr Address of malloc function in target process
 * @param free_addr Address of free function in target process
 * @param dlopen_addr Address of dlopen function in target process
 */
void inject_shared_library(long malloc_addr, long free_addr, long dlopen_addr,
                           long library_path_length) {
  // Optimized assembly code with macro usage for simplified operations
  asm(
      // Efficient stack alignment and register preservation
      "and $0xfffffffffffffff0, %%rsp \n" // 16-byte stack alignment
      "push %%r9 \n"  // to enforce stack alignment, 4 registers are reserved
      "push %%r8 \n"  // Save r8 for temporary use
      "push %%rsi \n" // Save free() address (will be 1st arg to free)
      "push %%rdx \n" // Save dlopen() address (will be 1st arg to dlopen)
      "mov %%rcx, %%r8 \n" // Copy malloc address to r8 (safekeeping)
      "callq *%%r8 \n"     // Call malloc (return value discarded)
      "int $3 \n"

      // Optimized dlopen execution sequence
      "pop %%r8 \n"         // Restore dlopen's address to r8
      "push %%rax \n"       // Push malloc's result for later free
      "mov %%rax, %%rdi \n" // Transfer malloc result as dlopen's 1st arg (path)
      "mov $0x1, %%rsi \n"  // Set RTLD_LAZY flag as dlopen's 2nd arg
      "callq *%%r8 \n"      // Execute dlopen (library loading)
      "int $3 \n"

      // Streamlined free execution with register cleanup
      "pop %%rdi \n"        // Restore malloc's return address
      "pop %%r8 \n"         // Retrieve free address
      "xor %%rsi, %%rsi \n" // Zero rsi (prevent accidental frees)
      "callq *%%r8 \n"      // Execute free (memory cleanup)
      "pop %%r8 \n"         // Final r8 restoration
      "pop %%r9 \n"         // Final r9 restoration
      :
      :
      : "memory", "rax", "rcx", "rdx", "rdi", "rsi", "r8", "r9");
}

/**
 * @brief Marks the end of inject_shared_library function for size calculation
 *
 * This function's only purpose is to be contiguous to inject_shared_library(),
 * so that we can use its address to more precisely figure out how long
 * inject_shared_library() is.
 */
void inject_shared_library_end() {
  // Intentionally empty - used only for calculating function size
}

/**
 * @brief Constructs a LibraryInjector instance
 *
 * Initializes the LibraryInjector with the target process identifier and
 * library file path. Also initializes the ProcessTracer for the target process.
 *
 * @param target_process_id PID of the target process to inject
 * @param shared_library_file_path File path of the shared library to inject
 */
LibraryInjector::LibraryInjector(pid_t target_process_id,
                                 const std::string &shared_library_file_path,
                                 bool debug_mode)
    : target_process_id_(target_process_id),
      library_file_path_(shared_library_file_path),
      process_tracer_(target_process_id, debug_mode) {}

/**
 * @brief Cleans up resources used by the LibraryInjector
 *
 * The ProcessTracer destructor will handle cleanup of any attached processes.
 */
LibraryInjector::~LibraryInjector() {}

/**
 * @brief Performs the complete library injection process
 *
 * This function performs the complete injection process:
 * 1. Initializes the injection environment by attaching to the process and
 * getting registers
 * 2. Resolves necessary function addresses in the target process
 * 3. Sets up registers for the injection
 * 4. Orchestrates the injection sequence
 *
 * @return true if injection was successful, false otherwise
 */
ExitCode LibraryInjector::performInjection() {
  long code_injection_address = 0;
  REG_TYPE original_registers, working_registers;

  // Initialize injection environment
  ExitCode initialize_code = initializeInjectionEnvironment(
      code_injection_address, &original_registers, &working_registers);
  if (initialize_code != ExitCode::SUCCESS) {
    if (initialize_code == ExitCode::GET_REGISTERS_AFTER_ATTACH_FAILED) {
      process_tracer_.detach();
    }
    return initialize_code;
  }

  // Get libc addresses for target process
  pid_t current_process_identifier = getpid();
  long current_libc_base_address =
      ProcessUtils::getLibcBaseAddress(current_process_identifier);

  long malloc_function_address = ProcessUtils::resolveFunctionAddress("malloc");
  long dlopen_function_address =
      ProcessUtils::resolveFunctionAddress("__libc_dlopen_mode");
  if (!dlopen_function_address) {
    dlopen_function_address = ProcessUtils::resolveFunctionAddress("dlopen");
  }
  long free_function_address = ProcessUtils::resolveFunctionAddress("free");

  // Debug output if enabled
  if (process_tracer_.isDebugMode()) {
    printf("[DEBUG] PyFlightProfiler: malloc address: 0x%lx, dlopen address: "
           "0x%lx, free address: 0x%lx\n",
           malloc_function_address, dlopen_function_address,
           free_function_address);
  }

  // Calculate offsets
  long malloc_address_offset =
      malloc_function_address - current_libc_base_address;
  long free_address_offset = free_function_address - current_libc_base_address;
  long dlopen_address_offset =
      dlopen_function_address - current_libc_base_address;

  // Get target process libc address and calculate function addresses
  long target_libc_base_address =
      ProcessUtils::getLibcBaseAddress(target_process_id_);

  long target_malloc_function_address =
      target_libc_base_address + malloc_address_offset;
  long target_free_function_address =
      target_libc_base_address + free_address_offset;
  long target_dlopen_function_address =
      target_libc_base_address + dlopen_address_offset;

  working_registers.rdi = library_file_path_.length() + 1;
  working_registers.rsi = target_free_function_address;
  working_registers.rdx = target_dlopen_function_address;
  working_registers.rcx = target_malloc_function_address;

  if (!process_tracer_.setRegisters(&working_registers)) {
    process_tracer_.detach();
    return ExitCode::SET_INJECTED_SHELLCODE_REGISTERS_FAILED;
  }

  // Orchestrate injection sequence
  ExitCode injection_result = orchestrateInjectionSequence(
      code_injection_address, target_malloc_function_address,
      target_free_function_address, target_dlopen_function_address,
      library_file_path_.length() + 1, &original_registers);

  return injection_result;
}

/**
 * @brief Initialize injection environment by attaching to the process and
 * setting up registers
 *
 * This function:
 * 1. Attaches to the target process
 * 2. Gets the current register state
 * 3. Finds a suitable memory address for code injection
 * 4. Sets up registers for the injection
 *
 * @param code_injection_address Reference to store the address where code will
 * be injected
 * @param original_registers Pointer to store the original register state
 * @param working_registers Pointer to store the modified register state
 * @return true if initialization was successful, false otherwise
 */
ExitCode
LibraryInjector::initializeInjectionEnvironment(long &code_injection_address,
                                                REG_TYPE *original_registers,
                                                REG_TYPE *working_registers) {
  // Attach to process
  if (!process_tracer_.attach()) {
    return ExitCode::ATTACH_FAILED;
  }

  // Get current registers
  if (!process_tracer_.getRegisters(original_registers)) {
    return ExitCode::GET_REGISTERS_AFTER_ATTACH_FAILED;
  }

  // Copy original registers to working registers
  *working_registers = *original_registers;

  // Find a good address to copy code to.
  // The findFreeMemoryAddress function returns the END of the first executable
  // region minus a safe offset, placing shellcode in the alignment padding area
  // that is typically unused but still has execute permissions.
  code_injection_address =
      ProcessUtils::findFreeMemoryAddress(target_process_id_) + 8;

  if (process_tracer_.isDebugMode()) {
    std::cout << "[DEBUG] PyFlightProfiler: Using injection address at 0x"
              << std::hex << code_injection_address << std::dec << std::endl;
  }

  // Set the target's rip to the injection address
  // Advance by 2 bytes because rip gets incremented by the size of the current
  // instruction
  working_registers->rip = code_injection_address + 2;
  return ExitCode::SUCCESS;
}

/**
 * @brief Create shellcode payload for library injection
 *
 * This function:
 * 1. Calculates the size of the inject_shared_library function
 * 2. Locates the return instruction offset
 * 3. Creates a buffer with NOP padding
 * 4. Copies the injection function code to the buffer
 * 5. Overwrites the return instruction with an INT 3 breakpoint
 *
 * @param payload_size Reference to store the size of the generated shellcode
 * @param return_instruction_offset Reference to store the offset of the return
 * instruction
 * @return Vector containing the generated shellcode
 */
std::vector<char>
LibraryInjector::createShellcodePayload(size_t &payload_size,
                                        intptr_t &return_instruction_offset) {
  // Figure out the size of inject_shared_library() so we know how big of a
  // buffer to allocate.
  payload_size =
      (intptr_t)inject_shared_library_end - (intptr_t)inject_shared_library + 2;

  // Also figure out where the RET instruction at the end of
  // inject_shared_library() lies so that we can overwrite it with an INT 3 in
  // order to break back into the target process.
  return_instruction_offset = (intptr_t)ProcessUtils::locateReturnInstruction(
                                  (void *)inject_shared_library_end) -
                              (intptr_t)inject_shared_library;

  // Set up a buffer to hold the code we're going to inject into the target
  // process.
  std::vector<char> shellcode_payload(payload_size, 0);

  shellcode_payload[0] =
      0x90; // fill with NOP, because when inject a process stuck in syscall,
  shellcode_payload[1] = 0x90; // rip will normally decrease by 2, so fill top
                               // two bytes with nop instruction

  // Copy the code of inject_shared_library() to a buffer.
  memcpy(shellcode_payload.data() + 2, (void *)inject_shared_library,
         payload_size - 3);

  // Overwrite the RET instruction with an INT 3.
  shellcode_payload[return_instruction_offset + 2] =
      0xcc; // 0xcc is the opcode for INT 3
  return shellcode_payload;
}

/**
 * @brief Orchestrate the injection sequence
 *
 * This function performs the complete injection sequence:
 * 1. Creates shellcode payload
 * 2. Backs up original data at the injection address
 * 3. Deploys the shellcode
 * 4. Executes the injected code
 * 5. Handles the malloc() call and library path copying
 * 6. Calls __libc_dlopen_mode to load the library
 * 7. Frees the allocated buffer
 * 8. Confirms the injection success
 *
 * @param injection_address Address where the shellcode will be injected
 * @param malloc_function_address Address of malloc function in target process
 * @param free_function_address Address of free function in target process
 * @param dlopen_function_address Address of dlopen function in target process
 * @param library_path_string_length Length of the library path string
 * @param initial_registers Pointer to the original register state
 * @return true if injection was successful, false otherwise
 */
ExitCode LibraryInjector::orchestrateInjectionSequence(
    long injection_address, long malloc_function_address,
    long free_function_address, long dlopen_function_address,
    int library_path_string_length, REG_TYPE *initial_registers) {
  // Create shellcode payload
  size_t shellcode_byte_size;
  intptr_t return_offset;
  std::vector<char> shellcode_payload =
      createShellcodePayload(shellcode_byte_size, return_offset);

  // Backup original data at injection address
  std::vector<char> backup_memory_data(shellcode_byte_size);
  if (!process_tracer_.readMemory(injection_address, backup_memory_data.data(),
                                  shellcode_byte_size)) {
    process_tracer_.recoverInjection(injection_address,
                                     backup_memory_data.data(),
                                     shellcode_byte_size, initial_registers);
    return ExitCode::READ_TARGET_MEMORY_FAILED;
  }

  // Deploy shellcode
  if (!process_tracer_.writeMemory(injection_address, shellcode_payload.data(),
                                   shellcode_payload.size())) {
    // Restore state and detach on failure
    process_tracer_.recoverInjection(injection_address,
                                     backup_memory_data.data(),
                                     shellcode_byte_size, initial_registers);
    return ExitCode::WRITE_SHELLCODE_TO_TARGET_MEMORY_FAILED;
  }

  // Now that the new code is in place, let the target run our injected code.
  if (!process_tracer_.continueExecution()) {
    // Restore state and detach on failure
    process_tracer_.recoverInjection(injection_address,
                                     backup_memory_data.data(),
                                     shellcode_byte_size, initial_registers);
    return ExitCode::ERROR_IN_EXECUTE_MALLOC;
  }

  // At this point, the target should have run malloc(). Check its return value.
  REG_TYPE malloc_registers_state;
  if (!process_tracer_.getRegisters(&malloc_registers_state)) {
    process_tracer_.recoverInjection(injection_address,
                                     backup_memory_data.data(),
                                     shellcode_byte_size, initial_registers);
    return ExitCode::GET_MALLOC_REGISTERS_FAILED;
  }

  unsigned long long target_buffer_address = malloc_registers_state.rax;
  if (target_buffer_address == 0) {
    process_tracer_.recoverInjection(injection_address,
                                     backup_memory_data.data(),
                                     shellcode_byte_size, initial_registers);
    return ExitCode::MALLOC_RETURN_ZERO;
  }

  // Copy the path to the shared library to the buffer allocated by malloc in
  // the target process.
  if (!process_tracer_.writeMemory(target_buffer_address,
                                   library_file_path_.c_str(),
                                   library_path_string_length)) {
    process_tracer_.recoverInjection(injection_address,
                                     backup_memory_data.data(),
                                     shellcode_byte_size, initial_registers);
    return ExitCode::WRITE_LIBRARY_STR_TO_TARGET_MEMORY_FAILED;
  }

  // Continue the target's execution to call __libc_dlopen_mode.
  if (!process_tracer_.continueExecution()) {
    process_tracer_.recoverInjection(injection_address,
                                     backup_memory_data.data(),
                                     shellcode_byte_size, initial_registers);
    return ExitCode::ERROR_IN_EXECUTE_DLOPEN;
  }

  // Check the registers after calling dlopen.
  REG_TYPE dlopen_registers_state;
  if (!process_tracer_.getRegisters(&dlopen_registers_state)) {
    process_tracer_.recoverInjection(injection_address,
                                     backup_memory_data.data(),
                                     shellcode_byte_size, initial_registers);
    return ExitCode::GET_DLOPEN_REGISTERS_FAILED;
  }

  unsigned long long library_base_address = dlopen_registers_state.rax;
  if (library_base_address == 0) {
    process_tracer_.recoverInjection(injection_address,
                                     backup_memory_data.data(),
                                     shellcode_byte_size, initial_registers);
    return ExitCode::DLOPEN_RETURN_ZERO;
  }

  // As a courtesy, free the buffer that we allocated inside the target process.
  if (!process_tracer_.continueExecution()) {
    process_tracer_.recoverInjection(injection_address,
                                     backup_memory_data.data(),
                                     shellcode_byte_size, initial_registers);
    return ExitCode::ERROR_IN_EXECUTE_FREE;
  }

  // Confirm injection success and restore state
  return confirmInjectionSuccess(injection_address, backup_memory_data,
                                 shellcode_byte_size, initial_registers);
}

/**
 * @brief Confirm the injection success and restore the original process state
 *
 * This function:
 * 1. Restores the original process state using ProcessTracer's recoverInjection
 * 2. Checks if the library was successfully loaded
 *
 * @param injection_memory_location Address where the shellcode was injected
 * @param backup_memory_data Vector containing the original data at the
 * injection address
 * @param shellcode_byte_size Size of the shellcode
 * @param original_register_state Pointer to the original register state
 * @return true if the library was successfully loaded, false otherwise
 */
ExitCode LibraryInjector::confirmInjectionSuccess(
    long injection_memory_location, const std::vector<char> &backup_memory_data,
    size_t shellcode_byte_size, REG_TYPE *original_register_state) {
  // Restore the original state using ProcessTracer's recoverInjection for
  // consistency Create a temporary copy of the data for restoration
  std::vector<char> temp_data(backup_memory_data);
  if (!process_tracer_.recoverInjection(injection_memory_location,
                                        temp_data.data(), shellcode_byte_size,
                                        original_register_state)) {
    return ExitCode::ERROR_IN_EXECUTE_RECOVER_INJECTION;
  }

  // Check if the library was successfully loaded
  if (ProcessUtils::isLibraryLoaded(target_process_id_, library_file_path_)) {
    if (process_tracer_.isDebugMode()) {
      std::cout << "[INFO] PyFlightProfiler: library " << library_file_path_
                << " successfully loaded in process." << target_process_id_
                << std::endl;
    }
    return ExitCode::SUCCESS;
  } else {
    if (process_tracer_.isDebugMode()) {
      std::cout << "[INFO] PyFlightProfiler: library " << library_file_path_
                << " was not loaded in process." << target_process_id_
                << std::endl;
    }
    return ExitCode::ERROR_IN_VERIFY_SO_LOCATION;
  }
}

/**
 * @brief Extract the parent directory from a file path
 *
 * Modifies the input path to remove the filename, leaving only the directory
 * path.
 *
 * @param file_path Reference to the path string to modify
 */
void LibraryInjector::getParentDirectoryPath(std::string &file_path) {
  size_t last_slash_position = file_path.rfind('/');
  if (last_slash_position != std::string::npos) {
    file_path.erase(
        last_slash_position); // Remove everything after the last slash
  }
}
