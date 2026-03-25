#ifndef ATTACH_AGENT_H
#define ATTACH_AGENT_H

#include "ExitCode.h"
#include "ProcessTracer.h"
#include "ProcessUtils.h"
#include <memory>
#include <string>
#include <sys/user.h>
#include <vector>

/**
 * @brief Manages the attaching of profiler agent into target processes
 *
 * This class implements a comprehensive solution for attaching profiler agent
 * into target processes using advanced ptrace-based techniques. It handles
 * all aspects of the attach process including preparation, execution, and
 * verification.
 */
class AttachAgent {
public:
  /**
   * @brief Constructs an AttachAgent instance
   * @param target_process_id PID of the process to attach the agent into
   * @param shared_library_file_path File path of the shared library to load
   * @param debug_mode Enable debug logging
   */
  AttachAgent(pid_t target_process_id,
              const std::string &shared_library_file_path,
              bool debug_mode = false);

  /**
   * @brief Cleans up resources used by the AttachAgent
   */
  ~AttachAgent();

  /**
   * @brief Performs the complete agent attach process
   * @return ExitCode indicating success or failure
   */
  ExitCode performAttach();

private:
  // Core instance attributes
  pid_t target_process_id_;
  std::string library_file_path_;
  ProcessTracer process_tracer_;

  // Attach workflow methods
  ExitCode initializeAttachEnvironment(long &code_attach_address,
                                       REG_TYPE *original_registers,
                                       REG_TYPE *working_registers);
  ExitCode orchestrateAttachSequence(long attach_address,
                                     long malloc_function_address,
                                     long free_function_address,
                                     long dlopen_function_address,
                                     int library_path_string_length,
                                     REG_TYPE *initial_registers);
  ExitCode confirmAttachSuccess(long attach_memory_location,
                                const std::vector<char> &backup_memory_data,
                                size_t shellcode_byte_size,
                                REG_TYPE *original_register_state);

  // Shellcode generation methods
  std::vector<char> createShellcodePayload(size_t &payload_size,
                                           intptr_t &return_instruction_offset);

  // Path manipulation utilities
  void getParentDirectoryPath(std::string &file_path);
};

#endif // ATTACH_AGENT_H
