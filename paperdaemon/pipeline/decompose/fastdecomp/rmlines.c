/* A page's stroke blocks read in one pass, for remarkable/fastrm.py.

   A .rm page (version 6) is a header and then blocks, each framed as its length (uint32), a zero byte, its minimum and
   current versions and its type (uint8 each). A stroke block (type 5) is a run of tagged fields -- a tag is a varuint,
   (index << 4) | kind, kind 0xF an id (uint8, varuint), 0xC a sub-block (uint32 length), 0x8 eight bytes, 0x4 four --
   read here in the order and with the tags rmscene reads them (SceneItemBlock.from_stream, line_from_stream). The
   points are not copied: each stroke gives where its packed records start and how long they are, and Python takes
   them from the page's bytes as they are.

   rf_rm_blocks walks every block; for each it fills one row of RF_RM_COLS int64 (below). A stroke block that is not
   laid out as expected is marked (RM_ODD) for Python to hand to rmscene. -> the number of blocks, or -1 when the
   frames do not add up, or -2 when there are more blocks than rows. */
#include <stdint.h>
#include <string.h>

#include "rmfast.h"

enum { RM_TYPE, RM_START, RM_END, RM_VERSION, RM_ODD,
       RM_PARENT1, RM_PARENT2, RM_ITEM1, RM_ITEM2, RM_LEFT1, RM_LEFT2, RM_RIGHT1, RM_RIGHT2, RM_DELETED,
       RM_HAS_VALUE, RM_TOOL, RM_COLOR, RM_THICKNESS_BITS, RM_STARTING_BITS, RM_PTS_OFF, RM_PTS_LEN,
       RM_HAS_MOVE, RM_MOVE1, RM_MOVE2, RM_HAS_RGBA, RM_RGBA, RM_SUB_EXTRA_OFF, RM_SUB_EXTRA_LEN, RM_EXTRA_OFF, RM_EXTRA_LEN,
       RM_COLS_ };

typedef struct { const uint8_t *d; int64_t p, end; int bad; } rd;

static uint64_t vu(rd *r) {
    uint64_t v = 0; int sh = 0;
    for (;;) {
        if (r->p >= r->end || sh > 63) { r->bad = 1; return 0; }
        uint8_t b = r->d[r->p++];
        v |= (uint64_t)(b & 0x7F) << sh;
        sh += 7;
        if (!(b & 0x80)) return v;
    }
}

static int peek(rd *r, int idx, int kind) {               /* is the next tag this one? (nothing read) */
    rd t = *r;
    uint64_t x = vu(&t);
    return !t.bad && x == (uint64_t)((idx << 4) | kind);
}

static void tag(rd *r, int idx, int kind) {
    if (vu(r) != (uint64_t)((idx << 4) | kind)) r->bad = 1;
}

static void cid(rd *r, int idx, int64_t *a, int64_t *b) {
    tag(r, idx, 0xF);
    if (r->bad || r->p >= r->end) { r->bad = 1; return; }
    *a = r->d[r->p++];
    *b = (int64_t)vu(r);
}

static uint32_t u32(rd *r) {
    if (r->p + 4 > r->end) { r->bad = 1; return 0; }
    uint32_t v; memcpy(&v, r->d + r->p, 4); r->p += 4;
    return v;
}

static void line_block(const uint8_t *d, int64_t p, int64_t end, int64_t *row) {
    rd r = {d, p, end, 0};
    cid(&r, 1, &row[RM_PARENT1], &row[RM_PARENT2]);
    cid(&r, 2, &row[RM_ITEM1], &row[RM_ITEM2]);
    cid(&r, 3, &row[RM_LEFT1], &row[RM_LEFT2]);
    cid(&r, 4, &row[RM_RIGHT1], &row[RM_RIGHT2]);
    tag(&r, 5, 0x4);
    row[RM_DELETED] = u32(&r);
    if (r.bad) { row[RM_ODD] = 1; return; }
    if (peek(&r, 6, 0xC)) {
        tag(&r, 6, 0xC);
        int64_t n = u32(&r), sub_end = r.p + n;
        if (r.bad || sub_end > end || r.p >= end || d[r.p] != 3) { row[RM_ODD] = 1; return; }
        r.p++;
        row[RM_HAS_VALUE] = 1;
        tag(&r, 1, 0x4); row[RM_TOOL] = u32(&r);
        tag(&r, 2, 0x4); row[RM_COLOR] = u32(&r);
        tag(&r, 3, 0x8);
        if (r.p + 8 > end) { row[RM_ODD] = 1; return; }
        memcpy(&row[RM_THICKNESS_BITS], d + r.p, 8); r.p += 8;
        tag(&r, 4, 0x4); row[RM_STARTING_BITS] = u32(&r);
        tag(&r, 5, 0xC);
        int64_t k = u32(&r);
        if (r.bad || r.p + k > sub_end) { row[RM_ODD] = 1; return; }
        row[RM_PTS_OFF] = r.p; row[RM_PTS_LEN] = k; r.p += k;
        int64_t t1, t2;
        cid(&r, 6, &t1, &t2);                                  /* the timestamp rmscene reads and drops */
        if (end - r.p >= 3 && peek(&r, 7, 0xF)) { row[RM_HAS_MOVE] = 1; cid(&r, 7, &row[RM_MOVE1], &row[RM_MOVE2]); }
        if (r.p < sub_end && peek(&r, 8, 0x4)) { tag(&r, 8, 0x4); row[RM_HAS_RGBA] = 1; row[RM_RGBA] = u32(&r); }
        if (r.bad || r.p > sub_end) { row[RM_ODD] = 1; return; }
        row[RM_SUB_EXTRA_OFF] = r.p; row[RM_SUB_EXTRA_LEN] = sub_end - r.p;
        r.p = sub_end;
    }
    row[RM_EXTRA_OFF] = r.p; row[RM_EXTRA_LEN] = end - r.p;
}

int64_t rf_rm_blocks(const uint8_t *d, int64_t n, int64_t header, int64_t *rows, int64_t max_rows) {
    int64_t p = header, count = 0;
    while (p < n) {
        if (p + 8 > n) return -1;
        uint32_t len; memcpy(&len, d + p, 4);
        int64_t start = p + 8, end = start + len;
        if (end > n) return -1;
        if (count >= max_rows) return -2;
        int64_t *row = rows + count * RM_COLS_;
        memset(row, 0, sizeof(int64_t) * RM_COLS_);
        row[RM_TYPE] = d[p + 7]; row[RM_START] = start; row[RM_END] = end; row[RM_VERSION] = d[p + 6];
        if (row[RM_TYPE] == 5) line_block(d, start, end, row);
        count++;
        p = end;
    }
    return count;
}

int32_t rf_rm_cols(void) { return RM_COLS_; }
