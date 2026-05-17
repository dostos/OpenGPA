#ifndef BHDR_HTTP_POST_H
#define BHDR_HTTP_POST_H

/* Minimal synchronous HTTP POST client used by the native trace shim to
 * ship payloads at /api/v1/... to the engine. Blocking, fail-open (engine
 * down → returns error, does NOT crash the host app). No keep-alive, no
 * HTTPS, no chunked encoding. ~150 lines of C, zero new deps. */

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    BHDR_HTTP_OK = 0,
    BHDR_HTTP_ERR_DNS = -1,
    BHDR_HTTP_ERR_CONNECT = -2,
    BHDR_HTTP_ERR_SEND = -3,
    BHDR_HTTP_ERR_INVAL = -4,
} BhdrHttpError;

/* POST `body` (JSON) to http://host:port<path>.
 * If `auth_token` is non-NULL and non-empty, attaches Authorization: Bearer.
 * `path` should start with "/". Returns BHDR_HTTP_OK on success (regardless
 * of HTTP response code — we fire-and-forget), or a BhdrHttpError on
 * transport failure. Never blocks longer than a few seconds; never crashes. */
int bhdr_http_post_json(const char* host, int port,
                       const char* path,
                       const char* auth_token,
                       const char* body, size_t body_len);

#ifdef __cplusplus
}
#endif

#endif /* BHDR_HTTP_POST_H */
