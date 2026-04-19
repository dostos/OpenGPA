#ifndef GPA_IPC_CLIENT_H
#define GPA_IPC_CLIENT_H

#include <stdint.h>

/* Connect to engine. Uses GPA_SOCKET_PATH and GPA_SHM_NAME env vars.
 * Returns 0 on success, -1 on failure (engine not running — shim works as
 * passthrough). */
int gpa_ipc_connect(void);

/* Check if connected */
int gpa_ipc_is_connected(void);

/* Claim a shared memory write slot. Returns pointer to data area, or NULL if
 * no free slot. */
void* gpa_ipc_claim_slot(uint32_t* slot_index);

/* Commit a written slot with its data size */
void gpa_ipc_commit_slot(uint32_t slot_index, uint64_t size);

/* Send FRAME_READY message to engine */
void gpa_ipc_send_frame_ready(uint64_t frame_id, uint32_t slot_index);

/* Check if engine wants us to pause. Non-blocking. */
int gpa_ipc_should_pause(void);

/* Block until engine signals resume */
void gpa_ipc_wait_resume(void);

/* Disconnect */
void gpa_ipc_disconnect(void);

#endif /* GPA_IPC_CLIENT_H */
