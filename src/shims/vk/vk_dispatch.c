#define _GNU_SOURCE
#include "vk_dispatch.h"

#include <pthread.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

/* --------------------------------------------------------------------------
 * Simple open-addressing hash table for dispatch table lookup.
 * Keys are raw pointer values (dispatch keys extracted from Vulkan handles).
 * -------------------------------------------------------------------------- */

#define DISPATCH_TABLE_CAPACITY 64  /* power-of-two for masking */
#define DISPATCH_TABLE_MASK     (DISPATCH_TABLE_CAPACITY - 1)

/* --------------------------------------------------------------------------
 * Instance dispatch table registry
 * -------------------------------------------------------------------------- */

typedef struct {
    void               *key;
    GpaInstanceDispatch disp;
} InstanceEntry;

static InstanceEntry g_inst_table[DISPATCH_TABLE_CAPACITY];
static pthread_mutex_t g_inst_mutex = PTHREAD_MUTEX_INITIALIZER;

void gpa_instance_dispatch_store(VkInstance instance, GpaInstanceDispatch *disp) {
    void *key = gpa_dispatch_key(instance);
    pthread_mutex_lock(&g_inst_mutex);

    /* Linear probe insertion */
    size_t slot = ((uintptr_t)key >> 3) & DISPATCH_TABLE_MASK;
    for (size_t i = 0; i < DISPATCH_TABLE_CAPACITY; i++) {
        size_t idx = (slot + i) & DISPATCH_TABLE_MASK;
        if (g_inst_table[idx].key == NULL || g_inst_table[idx].key == key) {
            g_inst_table[idx].key  = key;
            g_inst_table[idx].disp = *disp;
            pthread_mutex_unlock(&g_inst_mutex);
            return;
        }
    }
    fprintf(stderr, "[OpenGPA-VK] instance dispatch table full!\n");
    pthread_mutex_unlock(&g_inst_mutex);
}

GpaInstanceDispatch *gpa_instance_dispatch_get(VkInstance instance) {
    void *key = gpa_dispatch_key(instance);
    pthread_mutex_lock(&g_inst_mutex);

    size_t slot = ((uintptr_t)key >> 3) & DISPATCH_TABLE_MASK;
    for (size_t i = 0; i < DISPATCH_TABLE_CAPACITY; i++) {
        size_t idx = (slot + i) & DISPATCH_TABLE_MASK;
        if (g_inst_table[idx].key == NULL) break;
        if (g_inst_table[idx].key == key) {
            GpaInstanceDispatch *ret = &g_inst_table[idx].disp;
            pthread_mutex_unlock(&g_inst_mutex);
            return ret;
        }
    }
    pthread_mutex_unlock(&g_inst_mutex);
    return NULL;
}

void gpa_instance_dispatch_remove(VkInstance instance) {
    void *key = gpa_dispatch_key(instance);
    pthread_mutex_lock(&g_inst_mutex);

    size_t slot = ((uintptr_t)key >> 3) & DISPATCH_TABLE_MASK;
    for (size_t i = 0; i < DISPATCH_TABLE_CAPACITY; i++) {
        size_t idx = (slot + i) & DISPATCH_TABLE_MASK;
        if (g_inst_table[idx].key == NULL) break;
        if (g_inst_table[idx].key == key) {
            g_inst_table[idx].key = NULL;
            break;
        }
    }
    pthread_mutex_unlock(&g_inst_mutex);
}

/* --------------------------------------------------------------------------
 * Device dispatch table registry
 * -------------------------------------------------------------------------- */

typedef struct {
    void             *key;
    GpaDeviceDispatch disp;
} DeviceEntry;

static DeviceEntry     g_dev_table[DISPATCH_TABLE_CAPACITY];
static pthread_mutex_t g_dev_mutex = PTHREAD_MUTEX_INITIALIZER;

void gpa_device_dispatch_store(VkDevice device, GpaDeviceDispatch *disp) {
    void *key = gpa_dispatch_key(device);
    pthread_mutex_lock(&g_dev_mutex);

    size_t slot = ((uintptr_t)key >> 3) & DISPATCH_TABLE_MASK;
    for (size_t i = 0; i < DISPATCH_TABLE_CAPACITY; i++) {
        size_t idx = (slot + i) & DISPATCH_TABLE_MASK;
        if (g_dev_table[idx].key == NULL || g_dev_table[idx].key == key) {
            g_dev_table[idx].key  = key;
            g_dev_table[idx].disp = *disp;
            pthread_mutex_unlock(&g_dev_mutex);
            return;
        }
    }
    fprintf(stderr, "[OpenGPA-VK] device dispatch table full!\n");
    pthread_mutex_unlock(&g_dev_mutex);
}

GpaDeviceDispatch *gpa_device_dispatch_get(VkDevice device) {
    void *key = gpa_dispatch_key(device);
    pthread_mutex_lock(&g_dev_mutex);

    size_t slot = ((uintptr_t)key >> 3) & DISPATCH_TABLE_MASK;
    for (size_t i = 0; i < DISPATCH_TABLE_CAPACITY; i++) {
        size_t idx = (slot + i) & DISPATCH_TABLE_MASK;
        if (g_dev_table[idx].key == NULL) break;
        if (g_dev_table[idx].key == key) {
            GpaDeviceDispatch *ret = &g_dev_table[idx].disp;
            pthread_mutex_unlock(&g_dev_mutex);
            return ret;
        }
    }
    pthread_mutex_unlock(&g_dev_mutex);
    return NULL;
}

void gpa_device_dispatch_remove(VkDevice device) {
    void *key = gpa_dispatch_key(device);
    pthread_mutex_lock(&g_dev_mutex);

    size_t slot = ((uintptr_t)key >> 3) & DISPATCH_TABLE_MASK;
    for (size_t i = 0; i < DISPATCH_TABLE_CAPACITY; i++) {
        size_t idx = (slot + i) & DISPATCH_TABLE_MASK;
        if (g_dev_table[idx].key == NULL) break;
        if (g_dev_table[idx].key == key) {
            g_dev_table[idx].key = NULL;
            break;
        }
    }
    pthread_mutex_unlock(&g_dev_mutex);
}

void gpa_dispatch_init(void) {
    memset(g_inst_table, 0, sizeof(g_inst_table));
    memset(g_dev_table,  0, sizeof(g_dev_table));
}

void gpa_dispatch_cleanup(void) {
    memset(g_inst_table, 0, sizeof(g_inst_table));
    memset(g_dev_table,  0, sizeof(g_dev_table));
}
