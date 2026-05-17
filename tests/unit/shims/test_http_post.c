/* Unit tests for the minimal HTTP POST client (src/shims/gl/http_post.c).
 * Uses assert() — no external framework. */

#define _GNU_SOURCE
#include "src/shims/gl/http_post.h"

#include <arpa/inet.h>
#include <assert.h>
#include <netinet/in.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

/* ---- tiny single-shot TCP listener ------------------------------------- */

typedef struct {
    int  port;
    char buf[8192];
    int  len;
    int  done;
} Listener;

static void* listener_thread(void* arg) {
    Listener* L = (Listener*)arg;
    int ls = socket(AF_INET, SOCK_STREAM, 0);
    int one = 1;
    setsockopt(ls, SOL_SOCKET, SO_REUSEADDR, &one, sizeof(one));
    struct sockaddr_in sa = {0};
    sa.sin_family = AF_INET;
    sa.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    sa.sin_port = 0;
    if (bind(ls, (struct sockaddr*)&sa, sizeof(sa)) < 0) {
        perror("bind"); L->done = 1; return NULL;
    }
    socklen_t slen = sizeof(sa);
    getsockname(ls, (struct sockaddr*)&sa, &slen);
    L->port = ntohs(sa.sin_port);
    listen(ls, 1);

    /* Signal main thread we're listening. */
    __sync_synchronize();
    L->done = -1;  /* ready-to-accept sentinel */

    int cs = accept(ls, NULL, NULL);
    if (cs < 0) { close(ls); L->done = 1; return NULL; }

    int off = 0;
    while (off < (int)sizeof(L->buf) - 1) {
        ssize_t r = recv(cs, L->buf + off, sizeof(L->buf) - 1 - off, 0);
        if (r <= 0) break;
        off += (int)r;
        /* Keep reading until we've got headers + body. Crude heuristic:
         * look for Content-Length, then drain exactly that many body bytes. */
        char* hdr_end = strstr(L->buf, "\r\n\r\n");
        if (hdr_end) {
            *hdr_end = '\0';
            const char* cl = strstr(L->buf, "Content-Length:");
            *hdr_end = '\r';
            if (cl) {
                int want;
                if (sscanf(cl, "Content-Length: %d", &want) == 1) {
                    int have = off - (int)((hdr_end + 4) - L->buf);
                    if (have >= want) break;
                }
            }
        }
    }
    L->buf[off] = '\0';
    L->len = off;

    /* Send minimal response. */
    const char* resp = "HTTP/1.0 200 OK\r\nContent-Length: 0\r\n\r\n";
    send(cs, resp, strlen(resp), MSG_NOSIGNAL);
    close(cs);
    close(ls);
    L->done = 1;
    return NULL;
}

/* ------------------------------------------------------------------------ */

static void test_http_post_sends_valid_request(void) {
    Listener L = {0};
    pthread_t tid;
    pthread_create(&tid, NULL, listener_thread, &L);
    while (L.done == 0) { usleep(1000); }
    assert(L.port > 0);

    const char* body = "{\"hello\":\"world\"}";
    int rc = bhdr_http_post_json("127.0.0.1", L.port,
                                "/api/v1/test", NULL,
                                body, strlen(body));
    pthread_join(tid, NULL);
    assert(rc == BHDR_HTTP_OK);

    /* Verify what the listener received. */
    assert(strstr(L.buf, "POST /api/v1/test HTTP/1.0") != NULL);
    assert(strstr(L.buf, "Content-Type: application/json") != NULL);
    char cl[64];
    snprintf(cl, sizeof(cl), "Content-Length: %zu", strlen(body));
    assert(strstr(L.buf, cl) != NULL);
    assert(strstr(L.buf, body) != NULL);
    printf("PASS test_http_post_sends_valid_request\n");
}

static void test_http_post_fails_open_on_connection_refused(void) {
    /* Find an unused port by binding + closing. */
    int s = socket(AF_INET, SOCK_STREAM, 0);
    struct sockaddr_in sa = {0};
    sa.sin_family = AF_INET;
    sa.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    sa.sin_port = 0;
    bind(s, (struct sockaddr*)&sa, sizeof(sa));
    socklen_t slen = sizeof(sa);
    getsockname(s, (struct sockaddr*)&sa, &slen);
    int port = ntohs(sa.sin_port);
    close(s);

    int rc = bhdr_http_post_json("127.0.0.1", port,
                                "/api/v1/test", NULL,
                                "{}", 2);
    /* Must return an error, must NOT crash. */
    assert(rc != BHDR_HTTP_OK);
    assert(rc == BHDR_HTTP_ERR_CONNECT);
    printf("PASS test_http_post_fails_open_on_connection_refused\n");
}

static void test_http_post_honors_token(void) {
    Listener L = {0};
    pthread_t tid;
    pthread_create(&tid, NULL, listener_thread, &L);
    while (L.done == 0) { usleep(1000); }

    int rc = bhdr_http_post_json("127.0.0.1", L.port,
                                "/x", "secret-token-xyz",
                                "{}", 2);
    pthread_join(tid, NULL);
    assert(rc == BHDR_HTTP_OK);
    assert(strstr(L.buf, "Authorization: Bearer secret-token-xyz") != NULL);
    printf("PASS test_http_post_honors_token\n");
}

int main(void) {
    test_http_post_sends_valid_request();
    test_http_post_fails_open_on_connection_refused();
    test_http_post_honors_token();
    printf("All http_post tests passed.\n");
    return 0;
}
