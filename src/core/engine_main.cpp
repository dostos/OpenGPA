// Engine binary entry point
#include "src/core/engine.h"

#include <csignal>
#include <cstdio>
#include <string>

static gpa::Engine* g_engine = nullptr;

static void handle_signal(int /*sig*/) {
    if (g_engine) g_engine->stop();
}

int main(int argc, char** argv) {
    std::string socket_path = "/tmp/bhdr_engine.sock";
    std::string shm_name    = "/bhdr_ipc";

    if (argc > 1) socket_path = argv[1];
    if (argc > 2) shm_name    = argv[2];

    gpa::Engine engine(socket_path, shm_name);
    g_engine = &engine;

    ::signal(SIGINT,  handle_signal);
    ::signal(SIGTERM, handle_signal);

    std::printf("[gpa] engine starting on %s  shm=%s\n",
                socket_path.c_str(), shm_name.c_str());

    engine.run();

    std::printf("[gpa] engine stopped. frames stored: %zu\n",
                engine.frame_store().count());
    return 0;
}
