/* Minimal HTTP POST client for the OpenGPA native-trace shim. */

#define _GNU_SOURCE
#include "http_post.h"

#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <netdb.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>

/* Suppress SIGPIPE when peer closes — we don't want to kill the host app. */
static int send_all(int fd, const char* buf, size_t n) {
    size_t off = 0;
    while (off < n) {
        ssize_t w = send(fd, buf + off, n - off, MSG_NOSIGNAL);
        if (w < 0) {
            if (errno == EINTR) continue;
            return BHDR_HTTP_ERR_SEND;
        }
        off += (size_t)w;
    }
    return BHDR_HTTP_OK;
}

int bhdr_http_post_json(const char* host, int port,
                       const char* path,
                       const char* auth_token,
                       const char* body, size_t body_len) {
    if (!host || !path || (body_len > 0 && !body)) return BHDR_HTTP_ERR_INVAL;

    /* Resolve (numeric first, then getaddrinfo). We only support IPv4 for
     * simplicity — engine runs on 127.0.0.1 by default. */
    struct sockaddr_in sa;
    memset(&sa, 0, sizeof(sa));
    sa.sin_family = AF_INET;
    sa.sin_port = htons((uint16_t)port);
    if (inet_pton(AF_INET, host, &sa.sin_addr) != 1) {
        struct addrinfo hints = {0}, *res = NULL;
        hints.ai_family = AF_INET;
        hints.ai_socktype = SOCK_STREAM;
        if (getaddrinfo(host, NULL, &hints, &res) != 0 || !res) {
            if (res) freeaddrinfo(res);
            return BHDR_HTTP_ERR_DNS;
        }
        memcpy(&sa.sin_addr,
               &((struct sockaddr_in*)res->ai_addr)->sin_addr,
               sizeof(sa.sin_addr));
        freeaddrinfo(res);
    }

    int fd = socket(AF_INET, SOCK_STREAM | SOCK_CLOEXEC, 0);
    if (fd < 0) return BHDR_HTTP_ERR_CONNECT;

    /* 2s send + recv timeouts — we fail open if engine is slow. */
    struct timeval tv = {2, 0};
    setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    int one = 1;
    setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof(one));

    if (connect(fd, (struct sockaddr*)&sa, sizeof(sa)) < 0) {
        close(fd);
        return BHDR_HTTP_ERR_CONNECT;
    }

    /* Build and send the request. */
    char header[1024];
    int hlen;
    if (auth_token && auth_token[0]) {
        hlen = snprintf(header, sizeof(header),
            "POST %s HTTP/1.0\r\n"
            "Host: %s:%d\r\n"
            "User-Agent: beholder-shim/1.0\r\n"
            "Authorization: Bearer %s\r\n"
            "Content-Type: application/json\r\n"
            "Content-Length: %zu\r\n"
            "\r\n",
            path, host, port, auth_token, body_len);
    } else {
        hlen = snprintf(header, sizeof(header),
            "POST %s HTTP/1.0\r\n"
            "Host: %s:%d\r\n"
            "User-Agent: beholder-shim/1.0\r\n"
            "Content-Type: application/json\r\n"
            "Content-Length: %zu\r\n"
            "\r\n",
            path, host, port, body_len);
    }
    if (hlen < 0 || hlen >= (int)sizeof(header)) {
        close(fd);
        return BHDR_HTTP_ERR_INVAL;
    }

    int rc = send_all(fd, header, (size_t)hlen);
    if (rc == BHDR_HTTP_OK && body_len > 0) {
        rc = send_all(fd, body, body_len);
    }

    /* Drain response so the server can reset cleanly; ignore content. */
    if (rc == BHDR_HTTP_OK) {
        char scratch[512];
        for (int i = 0; i < 4; i++) {
            ssize_t r = recv(fd, scratch, sizeof(scratch), 0);
            if (r <= 0) break;
        }
    }

    close(fd);
    return rc;
}
