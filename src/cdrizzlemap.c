#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <Python.h>
#ifndef NPY_NO_DEPRECATED_API
#define NPY_NO_DEPRECATED_API NPY_1_10_API_VERSION
#endif
#include <numpy/npy_math.h>
#include <numpy/arrayobject.h>

#include "driz_portability.h"
#include "cdrizzlemap.h"
#include "cdrizzleutil.h"

#include <float.h>

static const double VERTEX_ATOL = 1.0e-12;
static const double APPROX_ZERO = 1.0e3 * DBL_MIN;
static const double MAX_INV_ERR = 0.03;


int
shrink_image_section(PyArrayObject *pixmap, int *xmin, int *xmax,
                     int *ymin, int *ymax) {
    int i, j, imin, imax, jmin, jmax, i1, i2, j1, j2;
    double *pv;

    j1 = *ymin;
    j2 = *ymax;
    i1 = *xmin;
    i2 = *xmax;

    imin = i2;
    jmin = j2;

    for (j = j1; j <= j2; ++j) {
        for (i = i1; i <= i2; ++i) {
            pv = (double *) PyArray_GETPTR3(pixmap, j, i, 0);
            if (!(npy_isnan(pv[0]) || npy_isnan(pv[1]))) {
                if (i < imin) {
                    imin = i;
                }
                if (j < jmin) {
                    jmin = j;
                }
                break;
            }
        }
    }

    imax = imin;
    jmax = jmin;

    for (j = j2; j >= j1; --j) {
        for (i = i2; i >= i1; --i) {
            pv = (double *) PyArray_GETPTR3(pixmap, j, i, 0);
            if (!(npy_isnan(pv[0]) || npy_isnan(pv[1]))) {
                if (i > imax) {
                    imax = i;
                }
                if (j > jmax) {
                    jmax = j;
                }
                break;
            }
        }
    }

    *xmin = imin;
    *xmax = imax;
    *ymin = jmin;
    *ymax = jmax;

    return (imin >= imax || jmin >= jmax);
}


/** ---------------------------------------------------------------------------
 * Map a point on the input image to the output image using
 * a mapping of the pixel centers between the two by interpolating
 * between the centers in the mapping
 *
 * pixmap: The mapping of the pixel centers from input to output image
 * xyin:   An (x,y) point on the input image
 * xyout:  The same (x, y) point on the output image (output)
 */

int
interpolate_point(struct driz_param_t *par, double xin, double yin,
                  double *xout, double *yout) {
    int ipix, jpix, npix, idim;
    int i0, j0, nx2, ny2;
    npy_intp *ndim;
    double x, y, x1, y1, f00, f01, f10, f11, g00, g01, g10, g11;
    double *p;
    PyArrayObject *pixmap;

    pixmap = par->pixmap;

    /* Bilinear interpolation from
       https://en.wikipedia.org/wiki/Bilinear_interpolation#On_the_unit_square
    */
    i0 = (int)xin;
    j0 = (int)yin;

    ndim = PyArray_DIMS(pixmap);
    nx2 = (int)ndim[1] - 2;
    ny2 = (int)ndim[0] - 2;

    // point is outside the interpolation range. adjust limits to extrapolate.
    if (i0 < 0) {
        i0 = 0;
    } else if (i0 > nx2) {
        i0 = nx2;
    }
    if (j0 < 0) {
        j0 = 0;
    } else if (j0 > ny2) {
        j0 = ny2;
    }

    x = xin - i0;
    y = yin - j0;
    x1 = 1.0 - x;
    y1 = 1.0 - y;

    p = get_pixmap(pixmap, i0, j0);
    f00 = p[0];
    g00 = p[1];

    p = get_pixmap(pixmap, i0 + 1, j0);
    f10 = p[0];
    g10 = p[1];

    p = get_pixmap(pixmap, i0, j0 + 1);
    f01 = p[0];
    g01 = p[1];

    p = get_pixmap(pixmap, i0 + 1, j0 + 1);
    f11 = p[0];
    g11 = p[1];

    *xout = f00 * x1 * y1 + f10 * x * y1 + f01 * x1 * y + f11 * x * y;
    *yout = g00 * x1 * y1 + g10 * x * y1 + g01 * x1 * y + g11 * x * y;

    if (npy_isnan(*xout) || npy_isnan(*yout)) return 1;

    return 0;
}

/** ---------------------------------------------------------------------------
 * Map an integer pixel position from the input to the output image.
 * Fall back on interpolation if the value at the point is undefined
 *
 * pixmap: The mapping of the pixel centers from input to output image
 * i        The index of the x coordinate
 * j        The index of the y coordinate
 * xyout:  The (x, y) point on the output image (output)
 */

int
map_pixel(
  PyArrayObject *pixmap,
  int           i,
  int           j,
  double        xyout[2]
  ) {

  int k;

  oob_pixel(pixmap, i, j);
  for (k = 0; k < 2; ++k) {
    xyout[k] = get_pixmap(pixmap, i, j)[k];

    if (npy_isnan(xyout[k])) return 1;
  }

  return 0;
}


int
map_pixel_fwd(PyArrayObject *pixmap, int i, int j, double *x, double *y) {
    double *pv = (double *) PyArray_GETPTR3(pixmap, j, i, 0);
    *x = *pv;
    *y = *(pv + 1);
    return ((npy_isnan(*x) || npy_isnan(*y)) ? 1 : 0);
}


/** ---------------------------------------------------------------------------
 * Map a point on the input image to the output image either by interpolation
 * or direct array acces if the input position is integral.
 *
 * pixmap: The mapping of the pixel centers from input to output image
 * xyin:   An (x,y) point on the input image
 * xyout:  The same (x, y) point on the output image (output)
 */

int
map_point(struct driz_param_t *par, const double xyin[2], double xyout[2]) {
    int i, j, status;
    double xin, yin, xout, yout;
    xin = xyin[0];
    yin = xyin[1];

    i = xyin[0];
    j = xyin[1];

    if ((double) i == xyin[0] && (double) j == xyin[1]) {
        if (i >= par->xmin && i <= par->xmax &&
            j >= par->ymin && j <= par->ymax) {
            status = map_pixel(par->pixmap, i, j, xyout);
        } else {
            return 1;
        }
    } else {
        status = interpolate_point(par, xin, yin, &xout, &yout);
    }

    xyout[0] = xout;
    xyout[1] = yout;

    return status;
}


int
map_point_new(struct driz_param_t *par, double xin, double yin,
              double *xout, double *yout) {
    int i, j, status;

    i = (int) xin;
    j = (int) yin;

    if ((double) i == xin && (double) j == yin) {
        return map_pixel_fwd(par->pixmap, i, j, xout, yout);
    } else {
        return interpolate_point(par, xin, yin, xout, yout);
    }
}


static int
eval_inversion(struct driz_param_t *par, double x, double y,
               double xyref[2], double *dist2) {
    double xout, yout, dx, dy;

    if (interpolate_point(par, x, y, &xout, &yout)) {
        return 1;
    }
    dx = xout - xyref[0];
    dy = yout - xyref[1];
    *dist2 = dx * dx + dy * dy;  // sqrt would be slower

    return 0;
}


int
invert_pixmap(struct driz_param_t *par, const double xyout[2], double xyin[2]) {
    // invert input 'xyout' (output image) coordinates iteratively to the input
    // image coordinates 'xyin' - output of this function.

    const double gr = 0.6180339887498948482;  // Golden Ratio: (sqrt(5)-1)/2
    const int nmax_iter = 50;
    int niter;
    double xmin, xmax, ymin, ymax, dx, dy, x1, x2, y1, y2;
    double d11, d12, d21, d22;

    xmin = ((double) par->xmin) - 0.5;
    xmax = ((double) par->xmax) + 0.5;
    ymin = ((double) par->ymin) - 0.5;
    ymax = ((double) par->ymax) + 0.5;
    dx = xmax;
    dy = ymax;

    niter = 0;

    while ((dx > MAX_INV_ERR || dy > MAX_INV_ERR) && niter < nmax_iter) {
        niter+=1;

        x1 = xmax - gr * dx;
        x2 = xmin + gr * dx;
        y1 = ymax - gr * dy;
        y2 = ymin + gr * dy;

        if (eval_inversion(par, x1, y1, xyout, &d11)) return 1;
        if (eval_inversion(par, x1, y2, xyout, &d12)) return 1;
        if (eval_inversion(par, x2, y1, xyout, &d21)) return 1;
        if (eval_inversion(par, x2, y2, xyout, &d22)) return 1;

        if (d11 < d12 && d11 < d21 && d11 < d22) {
            xmax = x2;
            ymax = y2;
        } else if (d12 < d11 && d12 < d21 && d12 < d22) {
            xmax = x2;
            ymin = y1;
        } else if (d21 < d11 && d21 < d12 && d21 < d22) {
            xmin = x1;
            ymax = y2;
        } else {
            xmin = x1;
            ymin = y1;
        }

        dx = xmax - xmin;
        dy = ymax - ymin;
    }

    xyin[0] = 0.5 * (xmin + xmax);
    xyin[1] = 0.5 * (ymin + ymax);

    if (niter == nmax_iter) return 1;

    return 0;
}


// computes modulus of a % b  (with b > 0) similar to Python. A more robust
// approach would be to do this: (((a % b) + b) % b). However the polygon
// intersection code will never have a < -1 and so a simplified and faster
// version was implemented that works for a >= -b.
inline int
mod(int a, int b) {
    return ((a + b) % b);
    // return (((a % b) + b) % b);
}

// test whether two vertices (points) are equal to within a specified
// absolute tolerance
static inline int
equal_vertices(struct vertex a, struct vertex b, double atol) {
    return (fabs(a.x - b.x) < atol && fabs(a.y - b.y) < atol);
}

// Z-axis/k-component of the cross product a x b
static inline double
area(struct vertex a, struct vertex b) {
    return (a.x * b.y - a.y * b.x);
}


// tests whether a point is in a half-plane of the vector going from
// vertex v_ to vertex v (including the case of the point lying on the
// vector (v_, v)). Specifically, it tests (v - v_) x (pt - v_) >= 0:
static inline int
is_point_in_hp(struct vertex pt, struct vertex v_, struct vertex v) {
    // (v - v_) x (pt - v_) = v x pt - v x v_ - v_ x pt + v_ x v_ =
    // = v x pt - v x v_ - v_ x pt
    return ((area(v, pt) - area(v_, pt) - area(v, v_)) >= -APPROX_ZERO);
}


// same as is_point_in_hp but tests strict inequality (point not on the vector)
static inline int
is_point_strictly_in_hp(const struct vertex pt, const struct vertex v_,
                        const struct vertex v) {
    return ( (area(v, pt) - area(v_, pt) - area(v, v_)) > APPROX_ZERO );
}


// returns 1 if all vertices from polygon p are inside polygon q or 0 if
// at least one vertex of p is outside of q.
static inline int
is_poly_contained(const struct polygon *p, const struct polygon *q) {
    int i, j;
    struct vertex *v_, *v;

    v_ = q->v + (q->npv - 1);
    v = q->v;

    for (i = 0; i < q->npv; i++) {
        for (j = 0; j < p->npv; j++) {
            if (!is_point_in_hp(p->v[j], *v_, *v)) {
                return 0;
            }
        }
        v_ = v;
        v++;
    }

    return 1;
}


// Append a vertex to the polygon's list of vertices and increment
// vertex count.
// return 1 if storage capacity is exceeded or 0 on success
static int
append_vertex(struct polygon *p, struct vertex v) {
    if ((p->npv > 0) && equal_vertices(p->v[p->npv - 1], v, VERTEX_ATOL)) {
        return 0;
    }
    if ((p->npv > 0) && equal_vertices(p->v[0], v, VERTEX_ATOL)) {
        return 1;
    }
    if (p->npv >= 2 * IMAGE_OUTLINE_NPTS) {
        return 1;
    }
    p->v[p->npv++] = v;
    return 0;
}


// remove midpoints (if any) - vertices that lie on a line connecting
// other two vertices
static void
simplify_polygon(struct polygon *p) {
    struct polygon pqhull;
    struct vertex dp, dq, *pv, *pv_, *pvnxt;
    int k;

    if (p->npv < 3) return;

    pqhull.npv = 0;

    pv_ = (struct vertex *)(p->v) + (p->npv - 1);
    pv = (struct vertex *)p->v;
    pvnxt = ((struct vertex *)p->v) + 1;

    for (k = 0; k < p->npv; k++) {
        dp.x = pvnxt->x - pv_->x;
        dp.y = pvnxt->y - pv_->y;
        dq.x = pv->x - pv_->x;
        dq.y = pv->y - pv_->y;

        if (fabs(area(dp, dq)) > APPROX_ZERO &&
            sqrt(dp.x * dp.x + dp.y * dp.y) > VERTEX_ATOL) {
            pqhull.v[pqhull.npv++] = *pv;
        }
        pv_ = pv;
        pv = pvnxt;
        pvnxt = ((struct vertex *)p->v) + (mod(2 + k, p->npv));
    }

    p->npv = pqhull.npv;
    for (k = 0; k < p->npv; k++) {
        p->v[k] = pqhull.v[k];
    }
}


static void
orient_ccw(struct polygon *p) {
    int k, m;
    struct vertex v1, v2, cm;

    if (p->npv < 3) return;

    // center of mass:
    for (k = 0; k < p->npv; ++k) {
        cm.x += p->v[k].x;
        cm.y += p->v[k].y;
    }
    cm.x /= p->npv;
    cm.y /= p->npv;

    // pick first two polygon vertices and subtract center:
    v1 = p->v[0];
    v2 = p->v[1];
    v1.x -= cm.x;
    v1.y -= cm.y;
    v2.x -= cm.x;
    v2.y -= cm.y;

    if (area(v1, v2) >= 0.0) {
        return;
    } else {
        for (k = 0; k < (p->npv / 2); ++k) {
            v1 = p->v[k];
            m = p->npv - 1 - k;
            p->v[k] = p->v[m];
            p->v[m] = v1;
        }
    }
}


int
intersect_convex_polygons(const struct polygon *p, const struct polygon *q,
                          struct polygon *pq) {

    int ip=0, iq=0, first_k, k;
    int inside=0;  // 0 - not set, 1 - "P", -1 - "Q"
    int pv_in_hpdq, qv_in_hpdp;
    struct vertex *pv, *pv_, *qv, *qv_, dp, dq, vi, first_intersect;
    double t, u, d, dot, signed_area;

    if ((p->npv < 3) || (q->npv < 3)) {
        return 1;
    }

    orient_ccw(p);
    orient_ccw(q);

    if (is_poly_contained(p, q)) {
        *pq = *p;
        simplify_polygon(pq);
        return 0;
    } else if (is_poly_contained(q, p)) {
        *pq = *q;
        simplify_polygon(pq);
        return 0;
    }

    pv_ = (struct vertex *)(p->v + (p->npv - 1));
    pv = (struct vertex *)p->v;
    qv_ = (struct vertex *)(q->v + (q->npv - 1));
    qv = (struct vertex *)q->v;

    first_k = -2;
    pq->npv = 0;

    for (k = 0; k <= 2 * (p->npv + q->npv); k++) {
        dp.x = pv->x - pv_->x;
        dp.y = pv->y - pv_->y;
        dq.x = qv->x - qv_->x;
        dq.y = qv->y - qv_->y;

        // https://en.wikipedia.org/wiki/Line–line_intersection
        t = (pv_->y - qv_->y) * dq.x - (pv_->x - qv_->x) * dq.y;
        u = (pv_->y - qv_->y) * dp.x - (pv_->x - qv_->x) * dp.y;
        signed_area = area(dp, dq);
        if (signed_area >= 0.0) {
            d = signed_area;
        } else {
            t = -t;
            u = -u;
            d = -signed_area;
        }

        pv_in_hpdq = is_point_strictly_in_hp(*qv_, *qv, *pv);
        qv_in_hpdp = is_point_strictly_in_hp(*pv_, *pv, *qv);

        if ((0.0 <= t) && (t <= d) && (0.0 <= u) && (u <= d) &&
            (d > APPROX_ZERO)) {
            t = t / d;
            u = u / d;
            vi.x = pv_->x + (pv->x - pv_->x) * t;
            vi.y = pv_->y + (pv->y - pv_->y) * t;

            if (first_k < 0) {
                first_intersect = vi;
                first_k = k;
                if (append_vertex(pq, vi)) break;
            } else if (equal_vertices(first_intersect, vi, VERTEX_ATOL)) {
                if (k > (first_k + 1)) {
                    break;
                }
                first_k = k;
            } else {
                if (append_vertex(pq, vi)) break;
            }

            if (pv_in_hpdq) {
                inside = 1;
            } else if (qv_in_hpdp) {
                inside = -1;
            }
        }

        // advance:
        if (d < 1.0e-12 && !pv_in_hpdq && !qv_in_hpdp) {
            if (inside == 1) {
                iq += 1;
                qv_ = qv;
                qv = q->v + mod(iq, q->npv);
            } else {
                ip += 1;
                pv_ = pv;
                pv = p->v + mod(ip, p->npv);
            }

        } else if (signed_area >= 0.0) {
            if (qv_in_hpdp) {
                if (inside == 1) {
                    if (append_vertex(pq, *pv)) break;
                }
                ip += 1;
                pv_ = pv;
                pv = p->v + mod(ip, p->npv);
            } else {
                if (inside == -1) {
                    if (append_vertex(pq, *qv)) break;
                }
                iq += 1;
                qv_ = qv;
                qv = q->v + mod(iq, q->npv);
            }

        } else {
            if (pv_in_hpdq) {
                if (inside == -1) {
                    if (append_vertex(pq, *qv)) break;
                }
                iq += 1;
                qv_ = qv;
                qv = q->v + mod(iq, q->npv);
            } else {
                if (inside == 1) {
                    if (append_vertex(pq, *pv)) break;
                }
                ip += 1;
                pv_ = pv;
                pv = p->v + mod(ip, q->npv);
            }
        }
    }

    simplify_polygon(pq);

    return 0;
}


static void
init_edge(struct edge *e, struct vertex v1, struct vertex v2, int position) {
    e->v1 = v1;
    e->v2 = v2;
    e->p = position;  // -1 for left-side edge and +1 for right-side edge
    e->m = (v2.x - v1.x) / (v2.y - v1.y);
    e->b = (v1.x * v2.y - v1.y * v2.x) / (v2.y - v1.y);
    e->c = e->b - copysign(0.5 + 0.5 * fabs(e->m), (double) position);
};


int
init_scanner(struct polygon *p, struct scanner *s, struct driz_param_t* par) {
    int k, i1, i2;
    int min_right, min_left, max_right, max_left;
    double min_y, max_y;

    s->left = NULL;
    s->right = NULL;
    s->nleft = 0;
    s->nright = 0;

    if (p->npv < 3) {
        // not a polygon
        s->overlap_valid = 0;
        return 1;
    }

    // find minimum/minima:
    min_y = p->v[0].y;
    min_left = 0;
    for (k = 1; k < p->npv; k++) {
        if (p->v[k].y < min_y) {
            min_left = k;
            min_y = p->v[k].y;
        }
    }

    i1 = mod(min_left - 1, p->npv);
    i2 = mod(min_left + 1, p->npv);
    min_right = ( p->v[i1].y < p->v[i2].y ) ? i1 : i2;
    if (p->v[min_right].y <= min_y * (1.0 + copysign(VERTEX_ATOL, min_y))) {
        if (p->v[min_left].x > p->v[min_right].x) {
            k = min_left;
            min_left = min_right;
            min_right = k;
        }
    } else {
        min_right = min_left;
    }

    // find maximum/maxima:
    max_y = p->v[0].y;
    max_right = 0;
    for (k = 1; k < p->npv; k++) {
        if (p->v[k].y > max_y) {
            max_right = k;
            max_y = p->v[k].y;
        }
    }

    i1 = mod(max_right - 1, p->npv);
    i2 = mod(max_right + 1, p->npv);
    max_left = ( p->v[i1].y > p->v[i2].y ) ? i1 : i2;
    if (p->v[max_left].y >= max_y * (1.0 - copysign(VERTEX_ATOL, max_y))) {
        if (p->v[max_left].x > p->v[max_right].x) {
            k = max_left;
            max_left = max_right;
            max_right = k;
        }
    } else {
        max_left = max_right;
    }

    // Left: start with minimum and move counter-clockwise:
    if (max_left > min_left) {
        min_left += p->npv;
    }
    s->nleft = min_left - max_left;

    for (k = 0; k < s->nleft; k++) {
        i1 = mod(min_left - k, p->npv);
        i2 = mod(i1 - 1, p->npv);
        init_edge(s->left_edges + k, p->v[i1], p->v[i2], -1);
    }

    // Right: start with minimum and move clockwise:
    if (max_right < min_right) {
        max_right += p->npv;
    }
    s->nright = max_right - min_right;

    for (k = 0; k < s->nright; k++) {
        i1 = mod(min_right + k, p->npv);
        i2 = mod(i1 + 1, p->npv);
        init_edge(s->right_edges + k, p->v[i1], p->v[i2], 1);
    }

    s->left = (struct edge *) s->left_edges;
    s->right = (struct edge *) s->right_edges;
    s->min_y = min_y;
    s->max_y = max_y;
    s->xmin = par->xmin;
    s->xmax = par->xmax;
    s->ymin = par->ymin;
    s->ymax = par->ymax;

    return 0;
}

/*
get_scanline_limits returns x-limits for an image row that fits between edges
(of a polygon) specified by the scanner structure.

This function is intended to be called successively with input 'y' *increasing*
from s->min_y to s->max_y.

Return code:
    0 - no errors;
    1 - scan ended (y reached the top vertex/edge);
    2 - pixel centered on y is outside of scanner's limits or image
        [0, height - 1];
    3 - limits (x1, x2) are equal (line with is 0).

*/
int
get_scanline_limits(struct scanner *s, int y, int *x1, int *x2) {
    double pyb, pyt;  // pixel top and bottom limits
    double xlb, xlt, xrb, xrt, edge_ymax, xmin, xmax;
    struct edge *el_max, *er_max;

    el_max = ((struct edge *) s->left_edges) + (s->nleft - 1);
    er_max = ((struct edge *) s->right_edges) + (s->nright - 1);

    if (s->ymax >= s->ymin && (y < 0 || y > s->ymax)) {
        return 2;
    }

    pyb = (double)y - 0.5;
    pyt = (double)y + 0.5;

    if (pyt <= s->min_y || pyb >= s->max_y + 1) {
        return 2;
    }

    if (s->left == NULL || s->right == NULL) {
        return 1;
    }

    while (pyb > s->left->v2.y) {
        if (s->left == el_max) {
            s->left = NULL;
            s->right = NULL;
            return 1;
        }
        ++s->left;
    };

    while (pyb > s->right->v2.y) {
        if (s->right == er_max) {
            s->left = NULL;
            s->right = NULL;
            return 1;
        }
        ++s->right;
    };

    xlb = s->left->m * y + s->left->c - MAX_INV_ERR;
    xrb = s->right->m * y + s->right->c + MAX_INV_ERR;

    edge_ymax = s->left->v2.y + 0.5 + MAX_INV_ERR;
    while (pyt > edge_ymax) {
        if (s->left == el_max) {
            s->left = NULL;
            s->right = NULL;
            return 1;
        }
        ++s->left;
        edge_ymax = s->left->v2.y + 0.5 + MAX_INV_ERR;
    };

    edge_ymax = s->right->v2.y + 0.5 + MAX_INV_ERR;
    while (pyt > edge_ymax) {
        if (s->right == er_max) {
            s->left = NULL;
            s->right = NULL;
            return 1;
        }
        ++s->right;
        edge_ymax = s->right->v2.y + 0.5 + MAX_INV_ERR;
    };

    xlt = s->left->m * y + s->left->c - MAX_INV_ERR;
    xrt = s->right->m * y + s->right->c + MAX_INV_ERR;

    xmin = s->xmin;// - 0.5;
    xmax = s->xmax;// + 0.5;
    if (s->xmax >= s->xmin) {
        if (xlb < xmin) {
            xlb = xmin;
        }
        if (xlt < xmin) {
            xlt = xmin;
        }
        if (xrb > xmax) {
            xrb = xmax;
        }
        if (xrt > xmax) {
            xrt = xmax;
        }
    }

    if (xlt >= xrt) {
        *x1 = (int)round(xlb);
        *x2 = (int)round(xrb);
        if (xlb >= xrb) {
            return 3;
        }
    } else if (xlb >= xrb) {
        *x1 = (int)round(xlt);
        *x2 = (int)round(xrt);
    } else {
        *x1 = (int)round((xlb > xlt) ? xlb : xlt);
        *x2 = (int)round((xrb < xrt) ? xrb : xrt);
    }

    return 0;
}


static int
map_to_output_vertex(struct driz_param_t* par, double x, double y,
                     struct vertex *v) {
    // convert coordinates to the output frame
    if (map_point_new(par, x, y, &v->x, &v->y)) {
        driz_error_set_message(par->error,
            "error computing input image bounding box");
        return 1;
    }

    return 0;
}


static int
map_to_input_vertex(struct driz_param_t* par, double x, double y,
                    struct vertex *v) {
    double xyin[2], xyout[2];
    char buf[MAX_DRIZ_ERROR_LEN];
    int n;
    // convert coordinates to the input frame
    xyout[0] = x;
    xyout[1] = y;
    if (invert_pixmap(par, xyout, xyin)) {
        n = sprintf(buf,
            "failed to invert pixel map at position (%.2f, %.2f)", x, y);
        if (n < 0) {
            strcpy(buf, "failed to invert pixel map");
        }
        driz_error_set_message(par->error, buf);
        return 1;
    }
    v->x = xyin[0];
    v->y = xyin[1];
    return 0;
}


int
init_image_scanner(struct driz_param_t* par, struct scanner *s,
                   int *ymin, int *ymax) {
    struct polygon p, q, pq, inpq;
    double  xyin[2], xyout[2];
    integer_t isize[2], osize[2];
    int ipoint;
    int k, n;
    npy_intp *ndim;

    // convert coordinates to the output frame and define a polygon
    // bounding the input image in the output frame:
    // inpq will be updated/overwritten later if coordinate mapping, inversion,
    // and polygon intersection is successful.
    inpq.npv = 4;
    inpq.v[0].x = par->xmin - 0.5;
    inpq.v[0].y = par->ymin - 0.5;
    inpq.v[1].x = par->xmax + 0.5;
    inpq.v[1].y = inpq.v[0].y;
    inpq.v[2].x = inpq.v[1].x;
    inpq.v[2].y = par->ymax + 0.5;
    inpq.v[3].x = inpq.v[0].x;
    inpq.v[3].y = inpq.v[2].y;

    if (map_to_output_vertex(par, inpq.v[0].x, inpq.v[0].y, p.v) ||
        map_to_output_vertex(par, inpq.v[1].x, inpq.v[1].y, p.v + 1) ||
        map_to_output_vertex(par, inpq.v[2].x, inpq.v[2].y, p.v + 2) ||
        map_to_output_vertex(par, inpq.v[3].x, inpq.v[3].y, p.v + 3)) {
        s->overlap_valid = 0;
        goto _setup_scanner;
    }
    p.npv = 4;

    // define a polygon bounding output image:
    ndim = PyArray_DIMS(par->output_data);
    q.npv = 4;
    q.v[0].x = -0.5;
    q.v[0].y = -0.5;
    q.v[1].x = (double)ndim[1] - 0.5;
    q.v[1].y = -0.5;
    q.v[2].x = (double)ndim[1] - 0.5;
    q.v[2].y = (double)ndim[0] - 0.5;
    q.v[3].x = -0.5;
    q.v[3].y = (double)ndim[0] - 0.5;

    // compute intersection of P and Q (in output frame):
    if (intersect_convex_polygons(&p, &q, &pq)) {
        s->overlap_valid = 0;
        goto _setup_scanner;
    }

    // convert coordinates of vertices of the intersection polygon
    // back to input image coordinate system:
    for (k = 0; k < pq.npv; k++) {
        if (map_to_input_vertex(par, pq.v[k].x, pq.v[k].y, &inpq.v[k])) {
            s->overlap_valid = 0;
            goto _setup_scanner;
        }
    }
    inpq.npv = pq.npv;
    s->overlap_valid = 1;
    orient_ccw(&inpq);

_setup_scanner:

    // initialize polygon scanner:
    driz_error_unset(par->error);
    n = init_scanner(&inpq, s, par);
    *ymin = MAX(0, (int)(s->min_y + 0.5 + 2.0 * MAX_INV_ERR));
    *ymax = MIN(s->ymax, (int)(s->max_y + 2.0 * MAX_INV_ERR));
    return n;
}
