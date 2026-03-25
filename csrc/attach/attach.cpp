#include "AttachAgent.h"
#include "ProcessUtils.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <limits.h>
#include <memory>
#include <sstream>
#include <unistd.h>

/**
 * @brief Extract the parent directory from a file system path
 *
 * Modifies the input path to remove the filename, leaving only the directory
 * path.
 *
 * @param file_system_path Reference to the path string to modify
 */
void extractParentDirectoryFromPath(std::string &file_system_path) {
  size_t last_slash_position = file_system_path.rfind('/');
  if (last_slash_position != std::string::npos) {
    file_system_path.erase(
        last_slash_position); // Remove everything after the last slash
  }
}

/**
 * @brief Main entry point for the profiler attach utility
 *
 * This program attaches the flight_profiler_agent.so library into a target
 * process using advanced ptrace-based techniques.
 *
 * Usage: ./attach <process_identifier>
 *
 * @param argument_count Number of command line arguments
 * @param argument_values Array of command line arguments
 * @return 0 on successful attach, 1 on failure
 */
int main(int argument_count, char **argument_values) {
  // Validate command line arguments
  if (argument_count < 2) {
    std::cout << "Invalid attach command without target process identifier "
                 "provided, USAGE: ./attach process_id!"
              << std::endl;
    return 1;
  }

  // Parse target process identifier
  pid_t target_process_id = atoi(argument_values[1]);

  // Check for debug flag
  bool debug_mode = false;
  if (argument_count >= 3 && strcmp(argument_values[2], "--debug") == 0) {
    debug_mode = true;
  }

  // Retrieve the executable path
  char executable_file_path[PATH_MAX];
  ssize_t path_length = readlink("/proc/self/exe", executable_file_path,
                                 sizeof(executable_file_path) - 1);

  if (path_length == -1) {
    perror("readlink error");
    return 1;
  }
  executable_file_path[path_length] = '\0';

  // Extract parent directory
  std::string execution_path_string(executable_file_path);
  extractParentDirectoryFromPath(execution_path_string);

  // Construct full library path
  std::string full_shared_library_path =
      execution_path_string + "/flight_profiler_agent.so";

  // Resolve the real path
  char *library_file_path_cstring =
      realpath(full_shared_library_path.c_str(), nullptr);
  if (!library_file_path_cstring) {
    std::cerr << "Cannot locate file \"" << full_shared_library_path << "\""
              << std::endl;
    return 1;
  }

  std::string library_file_path(library_file_path_cstring);
  free(library_file_path_cstring);

  // Create and execute the attach agent
  AttachAgent attach_agent(target_process_id, library_file_path, debug_mode);

  return static_cast<int>(attach_agent.performAttach());
}
