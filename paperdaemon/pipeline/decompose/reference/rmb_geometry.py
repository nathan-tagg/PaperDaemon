"""Single-plan contour pocketing, in source coordinates. No repair passes.

The classifier is unchanged. Every region, including its narrow lobes, uses
one nested family of constant-width loops. A subcell Euclidean distance field
keeps terminal lobes represented. Coordinates, not RGB, are fitted/smoothed.
No rendered image, coverage subtraction, leftover mask or patch pass is used.
"""
import math
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'vendor'))
import numpy as np
import cv2
# DETERMINISM: with Intel IPP on, cv2.distanceTransform's precise mode is not deterministic between runs
# (OpenCV issue 24082; two strokes of the robot moved by ~1e-6 between two identical decompositions). Off, every run
# is bit-identical, and the transform is OpenCV's own trueDistTrans, which the C port (fastdecomp/plan.c) reproduces.
if hasattr(cv2, "ipp"):
    cv2.ipp.setUseIPP(False)
import shapely
from shapely.geometry import Polygon, LineString, Point
from shapely.ops import polygonize
from skimage.measure import find_contours


def polygons(g):
    if g.is_empty:
        return []
    if g.geom_type == 'Polygon':
        return [g]
    return [p for sub in g.geoms for p in polygons(sub)] if hasattr(g, 'geoms') else []


def mask_polygon(mask, ppg):
    a = np.asarray(mask) != 0
    # Pixels are CELLS, not samples of separate scalar fields. Marching squares
    # at .5 cuts a triangle from every isolated corner. Four neighboring
    # colors then leave a diamond of unpainted paper between them.
    v = np.pad(a, ((0, 0), (1, 1)))
    y, x = np.nonzero(v[:, 1:] != v[:, :-1])
    vertical = np.stack([np.column_stack((x-.5, y-.5)),
                         np.column_stack((x-.5, y+.5))], axis=1)
    h = np.pad(a, ((1, 1), (0, 0)))
    y, x = np.nonzero(h[1:, :] != h[:-1, :])
    horizontal = np.stack([np.column_stack((x-.5, y-.5)),
                           np.column_stack((x+.5, y-.5))], axis=1)
    lines = shapely.linestrings(np.concatenate([vertical, horizontal]))
    faces = []
    for poly in polygonize(lines):
        point = poly.representative_point()
        x, y = int(round(point.x)), int(round(point.y))
        if 0 <= y < a.shape[0] and 0 <= x < a.shape[1] and a[y,x]:
            # Sub-pixel simplification, bounded in BOTH source and page units.
            faces.append(poly.simplify(min(.18, .45 / ppg), preserve_topology=True))
    return shapely.union_all(faces) if faces else Polygon()


def loops(g):
    for p in polygons(g):
        for r in [p.exterior, *p.interiors]:
            pts = list(r.coords)
            if len(pts) >= 4:
                # Repeat the first segment: its bevel closes the seam too.
                yield pts + [pts[1]]


def footprint(pts, width, flat):
    return LineString(pts).buffer(width/2, cap_style='flat' if flat else 'round',
                                 join_style='bevel' if flat else 'round', quad_segs=4)


# THE DIAMOND TEST WITHOUT GEOS (the C port has to give identical results). plan() skips a later
# minimum-width loop around an isolated cell when its flat/bevel footprint lies inside an already emitted
# solid one at the same center. That used shapely's buffer/covers/equals, whose vertex arithmetic a C port
# cannot reproduce bit for bit. The loops in question are axis-aligned diamonds with vertices (+-a, 0),
# (0, +-b); their bevel footprint of half-width r is the octagon of the four edges pushed out by r along
# their normals with the corners cut straight (the bevel), and it is solid -- no hole -- when the inward
# push swallows the diamond, i.e. when its inradius a*b/sqrt(a^2+b^2) is at most r. Containment of two such
# octagons is eight point-in-convex-polygon tests. A loop that is not a proper diamond (fewer than four
# distinct vertices) is never skipped and never stored. Ties (a shared extent) count as covered, as GEOS's
# exact predicates say. Measured against the GEOS version on the engine's own calls before the swap.
_DIAMOND_TOL = 1e-9


def diamond_of(rel):
    """rel: the 5 points (x, y) of a closed loop about its center, all on an axis -> (a, b) half-extents of a
    proper diamond, or None."""
    xs = sorted(set(float(x) for x, y in rel if float(y) == 0.0))
    ys = sorted(set(float(y) for x, y in rel if float(x) == 0.0))
    pts = set((float(x), float(y)) for x, y in rel)
    if len(pts) != 4 or len(xs) < 2 or len(ys) < 2:
        return None
    a, b = max(abs(xs[0]), abs(xs[-1])), max(abs(ys[0]), abs(ys[-1]))
    if a <= 0 or b <= 0 or pts != {(a, 0.0), (-a, 0.0), (0.0, b), (0.0, -b)}:
        return None
    return a, b


def diamond_octagon(a, b, r):
    """The bevel footprint's outer boundary, counterclockwise: each diamond edge pushed out by r."""
    h = math.sqrt(a * a + b * b)
    nx, ny = b / h, a / h          # the outward normal of the edge from (a, 0) to (0, b)
    out = []
    for sx, sy in ((1, 1), (-1, 1), (-1, -1), (1, -1)):
        # the edge in this quadrant runs from (sx*a, 0) to (0, sy*b) or back; push both ends out by r*n
        px, py = sx * nx * r, sy * ny * r
        e0, e1 = (sx * a + px, py), (px, sy * b + py)
        out.append((e0, e1) if sx * sy > 0 else (e1, e0))
    poly = []
    for e0, e1 in out:
        poly.extend([e0, e1])
    return poly


def diamond_solid(a, b, r):
    return a * b / math.sqrt(a * a + b * b) <= r + _DIAMOND_TOL


def octagon_covers(outer, inner):
    """Every vertex of `inner` inside or on the convex polygon `outer` (either orientation)."""
    n = len(outer)
    sign = 0.0
    for i in range(n):
        x0, y0 = outer[i]
        x1, y1 = outer[(i + 1) % n]
        x2, y2 = outer[(i + 2) % n]
        c = (x1 - x0) * (y2 - y1) - (y1 - y0) * (x2 - x1)
        if abs(c) > _DIAMOND_TOL:
            sign = 1.0 if c > 0 else -1.0
            break
    if sign == 0.0:
        return False
    for px, py in inner:
        for i in range(n):
            x0, y0 = outer[i]
            x1, y1 = outer[(i + 1) % n]
            if sign * ((x1 - x0) * (py - y0) - (y1 - y0) * (px - x0)) < -_DIAMOND_TOL:
                return False
    return True


def skeleton_paths(sk):
    """Trace without the triangular detours of an unconditional 8-neighbor graph.

    A diagonal edge is redundant when an orthogonal path already connects its
    pixels. At true junctions continue along the incoming tangent, without
    bridging separate components or inventing off-mask connectors.
    """
    yy,xx=np.nonzero(sk)
    points=set(zip(xx.tolist(),yy.tolist()))
    adj={}
    for x,y in sorted(points):
        near=[]
        for dx,dy in ((-1,0),(0,-1),(1,0),(0,1),(-1,-1),(1,-1),(1,1),(-1,1)):
            q=(x+dx,y+dy)
            if q not in points:continue
            if dx and dy and ((x+dx,y) in points or (x,y+dy) in points):continue
            near.append(q)
        adj[(x,y)]=near
    def edge(a,b):return (a,b) if a<b else (b,a)
    seen=set();out=[]
    for start in sorted(points,key=lambda p:(len(adj[p])!=1,p)):
        if not adj[start]:
            out.append([start,(start[0]+.01,start[1])]);continue
        for nxt in adj[start]:
            if edge(start,nxt) in seen:continue
            q=[start,nxt];seen.add(edge(start,nxt))
            while True:
                here=q[-1];choices=[p for p in adj[here] if edge(here,p) not in seen]
                if not choices:break
                prev=q[max(0,len(q)-5)]
                vx,vy=here[0]-prev[0],here[1]-prev[1]
                nxt=max(choices,key=lambda p:((p[0]-here[0])*vx+(p[1]-here[1])*vy)/math.hypot(p[0]-here[0],p[1]-here[1]))
                seen.add(edge(here,nxt));q.append(nxt)
                if nxt==start:break
            out.append(q)
    return out


def plan(mask, ppg, flat, max_page=30.):
    """One nested-loop plan, including small components and terminal lobes.

    The previous planner exempted narrow components from loops, although a
    thinned skeleton is NOT a coverage-complete medial axis. A three-pixel
    fleck could become a hollow perimeter with a short stroke at one end.
    Every component now participates in the same loop family. Spacing is
    limited by the CURRENT pen's reach, not the next (wider) pen: a lobe
    disappearing before the next level must already lie in this stroke.
    """
    a=np.asarray(mask)!=0
    if not a.any():return []
    unit=.25 if flat else .144
    minimum=1.0 if flat else .432
    factor=4 if ppg>3. else (2 if ppg>1. or not flat else 1)
    w=max(minimum,round(min(3.,ppg*(.70 if flat else .60))/unit)*unit)
    first_peak=.49 if factor==1 else .49-.5/factor
    depth=max(.01,min(first_peak,w/(2*ppg)-(.16 if flat else .02)))
    first_depth,first_width=depth,w
    # This refines the CELL GEOMETRY only. RGB is never interpolated or
    # reclassified. A source-grid EDT cannot resolve a one-cell-wide neck's
    # center: its apparent maximum depth is biased down by half a cell.
    cells=np.repeat(np.repeat(a,factor,axis=0),factor,axis=1)
    padded=np.pad(cells,1)
    dist=cv2.distanceTransform(padded.astype(np.uint8),cv2.DIST_L2,cv2.DIST_MASK_PRECISE)
    field=np.where(padded,(dist-.5)/factor,-.5/factor)
    limit=float(field.max())
    paths=[]
    # An isolated cell can produce several nested minimum-width diamonds.
    # Keep the original geometry, but omit a later loop only when its entire
    # flat/bevel footprint is contained in an already emitted, solid convex
    # footprint of this same color. This cannot add paint or remove coverage;
    # it is geometry-level redundancy elimination, not a rendered repair pass.
    small_footprints={}
    footprint_cache={}
    outer=True
    while depth<limit:
        for contour in find_contours(field,depth,fully_connected='high'):
            if len(contour)<4:continue
            q=(contour[:,::-1]-1+.5)/factor-.5
            # Fit vector coordinates AFTER color classification. This cannot
            # manufacture the extra palette bands caused by antialiasing RGB.
            # Only the silhouette-scale paths need the stronger stair filter;
            # photo washes retain their tight coverage tolerance.
            span=np.ptp(q,axis=0)
            # Washes reserve only .16 source cells of outer coverage slack.
            # The opaque silhouette fit (.32 simplification + .22 rounding)
            # can exceed that reserve, especially when a source cell spans
            # >3 page pixels. Keep washes on their existing tight fit at ALL
            # scales; opaque line smoothing is unchanged. This changes the
            # initial loop fit, not a coverage-driven repair or pen width.
            smooth=(not flat) and len(q)>12 and max(span)>6 and abs(cv2.contourArea(q.astype(np.float32)))>6
            eps=.32 if smooth else (min(.18,.22/ppg) if outer else min(.4,.60/ppg,.10*w/ppg))
            compact=cv2.approxPolyDP(q.astype(np.float32),eps,True)[:,0,:]
            if smooth and len(compact)>=4:
                # Bounded corner rounding, independent of long-segment length.
                prev=np.roll(compact,1,axis=0);nxt=np.roll(compact,-1,axis=0)
                v=prev-compact;u=nxt-compact
                v*=np.minimum(.22/np.maximum(np.linalg.norm(v,axis=1),1e-9),.20)[:,None]
                u*=np.minimum(.22/np.maximum(np.linalg.norm(u,axis=1),1e-9),.20)[:,None]
                compact=np.stack((compact+v,compact+u),axis=1).reshape(-1,2)
            if len(compact)>=3:q=np.vstack((compact,compact[0]))
            if flat and len(q)==5:
                center=(q.min(axis=0)+q.max(axis=0))*.5
                rel=q-center
                # Restrict the fast path to axis-aligned diamonds, including
                # their tiny floating-point asymmetry after coordinate fitting.
                if np.all((rel[:,0]==0)|(rel[:,1]==0)):
                    ab=diamond_of(rel)
                    if ab is not None:
                        ck=tuple(center)
                        r=(w/ppg)/2
                        shape=diamond_octagon(ab[0],ab[1],r)
                        previous=small_footprints.get(ck)
                        if previous is not None and previous[0]==w and octagon_covers(previous[1],shape):
                            continue
                        if diamond_solid(ab[0],ab[1],r):
                            if previous is None or octagon_covers(shape,previous[1]):small_footprints[ck]=(w,shape)
            pts=list(map(tuple,q))
            paths.append((pts+[pts[1]],w))
        # A sampled distance field underestimates the height of a medial
        # ridge between samples. Budget that subcell error BEFORE a lobe
        # disappears, not after looking for uncovered pixels. Width growth
        # is also bounded by this step, so inner loops cannot swell the edge.
        step=min(.42*w/ppg,max(.04/factor,w/(2*ppg)-.50/factor))
        depth += step
        next_w=min(max_page,w*1.6,first_width+2*(depth-first_depth)*ppg)
        w=max(minimum,math.floor((next_w+1e-8)/unit)*unit)
        outer=False
    return paths


FAST = None     # rm_model sets this to fastdecomp\rmfast.fill while the model runs: the planner in C, bit-identical
                # to plan() below. None = this file's Python.


def fill(mask, color, ppg, box, offset, grid, flat, api):
    if FAST is not None:
        return FAST(mask, color, ppg, box, offset, grid, flat, api)
    cw,ch=mask.size
    gw,gh=grid if grid else (cw,ch)
    max_page=api.K.HL_WIDTHS_PAGE[0] if flat else api.K.MARKER_WIDTHS_PAGE[0]
    result=[]
    for q,w in plan(mask,ppg,flat,max_page):
        (pts,)=api.place([[(x+offset[0],y+offset[1]) for x,y in q]],(gw,gh),box)
        if flat:
            field=api._hl_field(w)
            result.append((pts,[field]*len(pts),api.Pen.HIGHLIGHTER_2,api.PenColor.HIGHLIGHT,color))
        else:
            field=api._field(w)
            pen=api.Pen.FINELINER_2 if w<=api.K.FINELINER_MAX_PAGE else api.Pen.MARKER_2
            result.append((pts,[field]*len(pts),pen,color,None))
    return result
