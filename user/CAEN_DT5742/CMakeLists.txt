get_filename_component(EUDAQ_USERNAME ${CMAKE_CURRENT_LIST_DIR} NAME)
set(EUDAQ_MODULE module_${EUDAQ_USERNAME})

option(USER_CAEN_DT5742_BUILD "build user/CAEN_DT5742" OFF)

if(NOT USER_CAEN_DT5742_BUILD)
    message(STATUS "user/CAEN_DT5742 is NOT to be built (USER_CAEN_DT5742_BUILD=OFF)")
  return()
endif()

message(STATUS "user/CAEN_DT5742 is to be built (USER_CAEN_DT5742_BUILD=ON)")

add_subdirectory(module)
