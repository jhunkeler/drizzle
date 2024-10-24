import math
import os

import numpy as np
import pytest

from astropy import wcs
from astropy.io import fits
from drizzle import cdrizzle, resample, utils

TEST_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(TEST_DIR, 'data')


def bound_image(image):
    """
    Compute region where image is non-zero
    """
    coords = np.nonzero(image)
    ymin = coords[0].min()
    ymax = coords[0].max()
    xmin = coords[1].min()
    xmax = coords[1].max()
    return (ymin, ymax, xmin, xmax)


def centroid(image, size, center):
    """
    Compute the centroid of a rectangular area
    """
    ylo = int(center[0] - size / 2)
    yhi = min(ylo + size, image.shape[0])
    xlo = int(center[1] - size / 2)
    xhi = min(xlo + size, image.shape[1])

    yx1 = np.mgrid[ylo:yhi, xlo:xhi, 1:2]
    center = (yx1[..., 0] * image[ylo:yhi, xlo:xhi]).sum(
        axis=(1, 2),
        dtype=np.float64,
    )

    if center[2] == 0.0:
        return None

    center[0] /= center[2]
    center[1] /= center[2]
    return center


def centroid_close(list_of_centroids, size, point):
    """
    Find if any centroid is close to a point
    """
    for i in range(len(list_of_centroids) - 1, -1, -1):
        if (abs(list_of_centroids[i][0] - point[0]) < int(size / 2) and
                abs(list_of_centroids[i][1] - point[1]) < int(size / 2)):
            return 1

    return 0


def centroid_compare(centroid):
    return centroid[1]


def centroid_distances(image1, image2, amp, size):
    """
    Compute a list of centroids and the distances between them in two images
    """
    distances = []
    list_of_centroids = centroid_list(image2, amp, size)
    for center2 in list_of_centroids:
        center1 = centroid(image1, size, center2)
        if center1 is None:
            continue

        disty = center2[0] - center1[0]
        distx = center2[1] - center1[1]
        dist = math.sqrt(disty * disty + distx * distx)
        dflux = abs(center2[2] - center1[2])
        distances.append([dist, dflux, center1, center2])

    distances.sort(key=centroid_compare)
    return distances


def centroid_list(image, amp, size):
    """
    Find the next centroid
    """
    list_of_centroids = []
    points = np.transpose(np.nonzero(image > amp))
    for point in points:
        if not centroid_close(list_of_centroids, size, point):
            center = centroid(image, size, point)
            list_of_centroids.append(center)

    return list_of_centroids


def centroid_statistics(title, fname, image1, image2, amp, size):
    """
    write centroid statistics to compare differences btw two images
    """
    stats = ("minimum", "median", "maximum")
    images = (None, None, image1, image2)
    im_type = ("", "", "test", "reference")

    diff = []
    distances = centroid_distances(image1, image2, amp, size)
    indexes = (0, int(len(distances) / 2), len(distances) - 1)
    fd = open(fname, 'w')
    fd.write(f"*** {title:s} ***\n")

    if len(distances) == 0:
        diff = [0.0, 0.0, 0.0]
        fd.write("No matches!!\n")

    elif len(distances) == 1:
        diff = [distances[0][0], distances[0][0], distances[0][0]]

        fd.write("1 match\n")
        fd.write(
            f"distance = {distances[0][0]:f} "
            f"flux difference = {distances[0][1]:f}\n"
        )

        for j in range(2, 4):
            ylo = int(distances[0][j][0]) - 1
            yhi = int(distances[0][j][0]) + 2
            xlo = int(distances[0][j][1]) - 1
            xhi = int(distances[0][j][1]) + 2
            subimage = images[j][ylo:yhi, xlo:xhi]
            fd.write(
                f"\n{im_type[j]} image centroid = "
                f"({distances[0][j][0]:f}, {distances[0][j][1]:f}) "
                f"image flux = {distances[0][j][2]:f}\n"
            )
            fd.write(str(subimage) + "\n")

    else:
        fd.write(f"{len(distances)} matches\n")

        for k in range(3):
            i = indexes[k]
            diff.append(distances[i][0])
            fd.write(
                f"\n{stats[k]} distance = {distances[i][0]:f} "
                f"flux difference = {distances[i][1]:f}\n"
            )

            for j in range(2, 4):
                ylo = int(distances[i][j][0]) - 1
                yhi = int(distances[i][j][0]) + 2
                xlo = int(distances[i][j][1]) - 1
                xhi = int(distances[i][j][1]) + 2
                subimage = images[j][ylo:yhi, xlo:xhi]
                fd.write(
                    f"\n{stats[k]} {im_type[j]} image centroid = "
                    f"({distances[i][j][0]:f}, {distances[i][j][1]:f}) "
                    f"image flux = {distances[i][j][2]:f}\n"
                )
                fd.write(str(subimage) + "\n")

    fd.close()
    return tuple(diff)


def make_point_image(input_image, point, value):
    """
    Create an image with a single point set
    """
    output_image = np.zeros(input_image.shape, dtype=input_image.dtype)
    output_image[point] = value
    return output_image


def make_grid_image(input_image, spacing, value):
    """
    Create an image with points on a grid set
    """
    output_image = np.zeros(input_image.shape, dtype=input_image.dtype)

    shape = output_image.shape
    half_space = int(spacing / 2)
    for y in range(half_space, shape[0], spacing):
        for x in range(half_space, shape[1], spacing):
            output_image[y, x] = value

    return output_image


def read_image(filename):
    """
    Read the image from a fits file
    """
    path = os.path.join(DATA_DIR, filename)
    hdu = fits.open(path)

    image = hdu[1].data
    hdu.close()
    return image


def read_wcs(filename):
    """
    Read the wcs of a fits file
    """
    path = os.path.join(DATA_DIR, filename)
    hdu = fits.open(path)
    the_wcs = wcs.WCS(hdu[1].header)
    hdu.close()
    return the_wcs


def test_drizzle_defaults():
    n = 200
    in_shape = (n, n)

    # input coordinate grid:
    y, x = np.indices(in_shape, dtype=np.float64)

    # simulate data:
    in_sci = np.ones(in_shape, dtype=np.float32)
    in_wht = np.ones(in_shape, dtype=np.float32)

    # create a Drizzle object using all default parameters (except for 'kernel')
    driz = resample.Drizzle(
        kernel='square',
    )

    assert driz.out_img is None
    assert driz.out_wht is None
    assert driz.out_ctx is None
    assert driz.total_exptime == 0.0

    driz.add_image(
        in_sci,
        exptime=1.0,
        pixmap=np.dstack([x, y]),
        weight_map=in_wht,
    )

    pixmap = np.dstack([x + 1, y + 2])
    driz.add_image(
        3 * in_sci,
        exptime=1.0,
        pixmap=pixmap,
        weight_map=in_wht,
    )

    assert driz.out_img[0, 0] == 1
    assert driz.out_img[1, 0] == 1
    assert driz.out_img[2, 0] == 1
    assert driz.out_img[1, 1] == 1
    assert driz.out_img[1, 2] == 1
    assert (driz.out_img[2, 1] - 2.0) < 1.0e-14


def test_square_with_point(tmpdir):
    """
    Test do_driz square kernel with point
    """
    output_difference = str(tmpdir.join('difference_square_point.txt'))

    input_file = os.path.join(DATA_DIR, 'j8bt06nyq_flt.fits')
    output_template = os.path.join(DATA_DIR, 'reference_square_point.fits')

    insci = read_image(input_file)
    inwcs = read_wcs(input_file)
    insci = make_point_image(insci, (500, 200), 100.0)
    inwht = np.ones(insci.shape, dtype=insci.dtype)
    output_wcs = read_wcs(output_template)

    pixmap = utils.calc_pixmap(
        inwcs,
        output_wcs,
    )

    # ignore previous pscale and compute it the old way (only to make
    # tests work with old truth files and thus to show that new API gives
    # same results when equal definitions of the pixel scale is used):
    pscale = np.sqrt(
        np.sum(output_wcs.wcs.pc**2, axis=0)[0] /
        np.sum(inwcs.wcs.cd**2, axis=0)[0]
    )

    driz = resample.Drizzle(
        kernel='square',
        out_shape=output_wcs.array_shape,
        fillval=0.0,
    )
    driz.add_image(
        insci,
        exptime=1.0,
        pixmap=pixmap,
        weight_map=inwht,
        scale=pscale,
    )

    template_data = read_image(output_template)

    _, med_diff, max_diff = centroid_statistics(
        "square with point",
        output_difference,
        driz.out_img,
        template_data,
        20.0,
        8,
    )

    assert med_diff < 1.0e-6
    assert max_diff < 1.0e-5


@pytest.mark.parametrize(
    'kernel,fc',
    [
        ('square', True),
        ('point', True),
        ('turbo', True),
        ('lanczos2', False),
        ('lanczos3', False),
        ('gaussian', False),
    ],
)
def test_zero_input_weight(kernel, fc):
    """
    Test do_driz square kernel with grid
    """
    # initialize input:
    insci = np.ones((200, 400), dtype=np.float32)
    inwht = np.ones((200, 400), dtype=np.float32)
    inwht[:, 150:155] = 0

    # initialize output:
    outsci = np.zeros((210, 410), dtype=np.float32)
    outwht = np.zeros((210, 410), dtype=np.float32)
    outctx = np.zeros((210, 410), dtype=np.int32)

    # define coordinate mapping:
    pixmap = np.moveaxis(np.mgrid[1:201, 1:401][::-1], 0, -1)

    # resample:
    if fc:
        cdrizzle.tdriz(
            insci,
            inwht,
            pixmap,
            outsci,
            outwht,
            outctx,
            uniqid=1,
            xmin=0,
            xmax=400,
            ymin=0,
            ymax=200,
            pixfrac=1,
            kernel=kernel,
            in_units='cps',
            expscale=1,
            wtscale=1,
            fillstr='INDEF',
        )
    else:
        with pytest.warns(Warning):
            cdrizzle.tdriz(
                insci,
                inwht,
                pixmap,
                outsci,
                outwht,
                outctx,
                uniqid=1,
                xmin=0,
                xmax=400,
                ymin=0,
                ymax=200,
                pixfrac=1,
                kernel=kernel,
                in_units='cps',
                expscale=1,
                wtscale=1,
                fillstr='INDEF',
            )
        # pytest.xfail("Not a flux-conserving kernel")

    # check that no pixel with 0 weight has any counts:
    assert np.sum(np.abs(outsci[(outwht == 0)])) == 0.0


def test_square_with_grid(tmpdir):
    """
    Test do_driz square kernel with grid
    """
    output_difference = str(tmpdir.join('difference_square_grid.txt'))

    input_file = os.path.join(DATA_DIR, 'j8bt06nyq_flt.fits')
    output_template = os.path.join(DATA_DIR, 'reference_square_grid.fits')

    insci = read_image(input_file)
    inwcs = read_wcs(input_file)
    insci = make_grid_image(insci, 64, 100.0)

    inwht = np.ones(insci.shape, dtype=insci.dtype)
    output_wcs = read_wcs(output_template)

    pixmap = utils.calc_pixmap(
        inwcs,
        output_wcs,
    )
    pscale = utils.estimate_pixel_scale_ratio(
        inwcs,
        output_wcs,
        refpix_from=inwcs.wcs.crpix,
        refpix_to=output_wcs.wcs.crpix,
    )
    # ignore previous pscale and compute it the old way (only to make
    # tests work with old truth files and thus to show that new API gives
    # same results when equal definitions of the pixel scale is used):
    pscale = np.sqrt(
        np.sum(output_wcs.wcs.pc**2, axis=0)[0] /
        np.sum(inwcs.wcs.cd**2, axis=0)[0]
    )

    driz = resample.Drizzle(
        kernel='square',
        out_shape=output_wcs.array_shape,
        fillval=0.0,
    )
    driz.add_image(
        insci,
        exptime=1.0,
        pixmap=pixmap,
        weight_map=inwht,
        scale=pscale,
    )
    template_data = read_image(output_template)

    _, med_diff, max_diff = centroid_statistics(
        "square with grid",
        output_difference,
        driz.out_img,
        template_data,
        20.0,
        8,
    )
    assert med_diff < 1.0e-6
    assert max_diff < 1.0e-5


def test_turbo_with_grid(tmpdir):
    """
    Test do_driz turbo kernel with grid
    """
    output_difference = str(tmpdir.join('difference_turbo_grid.txt'))

    input_file = os.path.join(DATA_DIR, 'j8bt06nyq_flt.fits')
    output_template = os.path.join(DATA_DIR, 'reference_turbo_grid.fits')

    insci = read_image(input_file)
    inwcs = read_wcs(input_file)
    insci = make_grid_image(insci, 64, 100.0)
    inwht = np.ones(insci.shape, dtype=insci.dtype)
    output_wcs = read_wcs(output_template)

    pixmap = utils.calc_pixmap(
        inwcs,
        output_wcs,
    )
    pscale = utils.estimate_pixel_scale_ratio(
        inwcs,
        output_wcs,
        refpix_from=inwcs.wcs.crpix,
        refpix_to=output_wcs.wcs.crpix,
    )

    # ignore previous pscale and compute it the old way (only to make
    # tests work with old truth files and thus to show that new API gives
    # same results when equal definitions of the pixel scale is used):
    pscale = np.sqrt(
        np.sum(output_wcs.wcs.pc**2, axis=0)[0] /
        np.sum(inwcs.wcs.cd**2, axis=0)[0]
    )

    driz = resample.Drizzle(
        kernel='turbo',
        out_shape=output_wcs.array_shape,
        fillval=0.0,
    )
    driz.add_image(
        insci,
        exptime=1.0,
        pixmap=pixmap,
        weight_map=inwht,
        scale=pscale,
    )

    template_data = read_image(output_template)

    _, med_diff, max_diff = centroid_statistics(
        "turbo with grid",
        output_difference,
        driz.out_img,
        template_data,
        20.0,
        8,
    )

    assert med_diff < 1.0e-6
    assert max_diff < 1.0e-5


def test_gaussian_with_grid(tmpdir):
    """
    Test do_driz gaussian kernel with grid
    """
    output_difference = str(tmpdir.join('difference_gaussian_grid.txt'))

    input_file = os.path.join(DATA_DIR, 'j8bt06nyq_flt.fits')
    output_template = os.path.join(DATA_DIR, 'reference_gaussian_grid.fits')

    insci = read_image(input_file)
    inwcs = read_wcs(input_file)
    insci = make_grid_image(insci, 64, 100.0)
    inwht = np.ones(insci.shape, dtype=insci.dtype)
    output_wcs = read_wcs(output_template)

    pixmap = utils.calc_pixmap(
        inwcs,
        output_wcs,
    )
    pscale = utils.estimate_pixel_scale_ratio(
        inwcs,
        output_wcs,
        refpix_from=inwcs.wcs.crpix,
        refpix_to=output_wcs.wcs.crpix,
    )

    # ignore previous pscale and compute it the old way (only to make
    # tests work with old truth files and thus to show that new API gives
    # same results when equal definitions of the pixel scale is used):
    pscale = np.sqrt(
        np.sum(output_wcs.wcs.pc**2, axis=0)[0] /
        np.sum(inwcs.wcs.cd**2, axis=0)[0]
    )

    driz = resample.Drizzle(
        kernel='gaussian',
        out_shape=output_wcs.array_shape,
        fillval=0.0,
    )
    with pytest.warns(Warning):
        driz.add_image(
            insci,
            exptime=1.0,
            pixmap=pixmap,
            weight_map=inwht,
            scale=pscale,
        )

    template_data = read_image(output_template)

    _, med_diff, max_diff = centroid_statistics(
        "gaussian with grid",
        output_difference,
        driz.out_img,
        template_data,
        20.0,
        8,
    )

    assert med_diff < 1.0e-6
    assert max_diff < 2.0e-5


def test_lanczos_with_grid(tmpdir):
    """
    Test do_driz lanczos kernel with grid
    """
    output_difference = str(tmpdir.join('difference_lanczos_grid.txt'))

    input_file = os.path.join(DATA_DIR, 'j8bt06nyq_flt.fits')
    output_template = os.path.join(DATA_DIR, 'reference_lanczos_grid.fits')

    insci = read_image(input_file)
    inwcs = read_wcs(input_file)
    insci = make_grid_image(insci, 64, 100.0)
    inwht = np.ones(insci.shape, dtype=insci.dtype)
    output_wcs = read_wcs(output_template)

    pixmap = utils.calc_pixmap(
        inwcs,
        output_wcs,
    )
    pscale = utils.estimate_pixel_scale_ratio(
        inwcs,
        output_wcs,
        refpix_from=inwcs.wcs.crpix,
        refpix_to=output_wcs.wcs.crpix,
    )

    # ignore previous pscale and compute it the old way (only to make
    # tests work with old truth files and thus to show that new API gives
    # same results when equal definitions of the pixel scale is used):
    pscale = np.sqrt(
        np.sum(output_wcs.wcs.pc**2, axis=0)[0] /
        np.sum(inwcs.wcs.cd**2, axis=0)[0]
    )

    driz = resample.Drizzle(
        kernel='lanczos3',
        out_shape=output_wcs.array_shape,
        fillval=0.0,
    )
    with pytest.warns(Warning):
        driz.add_image(
            insci,
            exptime=1.0,
            pixmap=pixmap,
            weight_map=inwht,
            scale=pscale,
        )

    template_data = read_image(output_template)

    _, med_diff, max_diff = centroid_statistics(
        "lanczos with grid",
        output_difference,
        driz.out_img,
        template_data,
        20.0,
        8,
    )
    assert med_diff < 1.0e-6
    assert max_diff < 1.0e-5


def test_point_with_grid(tmpdir):
    """
    Test do_driz point kernel with grid
    """
    output_difference = str(tmpdir.join('difference_point_grid.txt'))

    input_file = os.path.join(DATA_DIR, 'j8bt06nyq_flt.fits')
    output_template = os.path.join(DATA_DIR, 'reference_point_grid.fits')

    insci = read_image(input_file)
    inwcs = read_wcs(input_file)
    insci = make_grid_image(insci, 64, 100.0)
    inwht = np.ones(insci.shape, dtype=insci.dtype)
    output_wcs = read_wcs(output_template)

    pixmap = utils.calc_pixmap(inwcs, output_wcs)

    driz = resample.Drizzle(kernel='point', out_shape=output_wcs.array_shape, fillval=0.0)
    driz.add_image(insci, exptime=1.0, pixmap=pixmap, weight_map=inwht)

    template_data = read_image(output_template)

    _, med_diff, max_diff = centroid_statistics(
        "point with grid",
        output_difference,
        driz.out_img,
        template_data,
        20.0,
        8,
    )
    assert med_diff < 1.0e-6
    assert max_diff < 1.0e-5


def test_blot_with_point(tmpdir):
    """
    Test do_blot with point image
    """
    output_difference = str(tmpdir.join('difference_blot_point.txt'))

    input_file = os.path.join(DATA_DIR, 'j8bt06nyq_flt.fits')
    output_template = os.path.join(DATA_DIR, 'reference_blot_point.fits')

    outsci = read_image(input_file)
    outwcs = read_wcs(input_file)
    outsci = make_point_image(outsci, (500, 200), 40.0)
    inwcs = read_wcs(output_template)

    pixmap = utils.calc_pixmap(inwcs, outwcs)

    # compute pscale the old way (only to make
    # tests work with old truth files and thus to show that new API gives
    # same results when equal definitions of the pixel scale is used):
    pscale = np.sqrt(
        np.sum(inwcs.wcs.pc**2, axis=0)[0] /
        np.sum(outwcs.wcs.cd**2, axis=0)[0]
    )

    blotted_image = resample.blot_image(
        outsci,
        pixmap=pixmap,
        pix_ratio=pscale,
        exptime=1.0,
        output_pixel_shape=inwcs.pixel_shape,
    )

    template_data = read_image(output_template)

    _, med_diff, max_diff = centroid_statistics(
        "blot with point",
        output_difference,
        blotted_image,
        template_data,
        20.0,
        16,
    )
    assert med_diff < 1.0e-6
    assert max_diff < 1.0e-5


def test_blot_with_default(tmpdir):
    """
    Test do_blot with default grid image
    """
    output_difference = str(tmpdir.join('difference_blot_default.txt'))

    input_file = os.path.join(DATA_DIR, 'j8bt06nyq_flt.fits')
    output_template = os.path.join(DATA_DIR, 'reference_blot_default.fits')

    outsci = read_image(input_file)
    outsci = make_grid_image(outsci, 64, 100.0)
    outwcs = read_wcs(input_file)
    inwcs = read_wcs(output_template)

    pixmap = utils.calc_pixmap(inwcs, outwcs)

    # compute pscale the old way (only to make
    # tests work with old truth files and thus to show that new API gives
    # same results when equal definitions of the pixel scale is used):
    pscale = np.sqrt(
        np.sum(inwcs.wcs.pc**2, axis=0)[0] /
        np.sum(outwcs.wcs.cd**2, axis=0)[0]
    )

    blotted_image = resample.blot_image(
        outsci,
        pixmap=pixmap,
        pix_ratio=pscale,
        exptime=1.0,
        output_pixel_shape=inwcs.pixel_shape,
    )

    template_data = read_image(output_template)

    _, med_diff, max_diff = centroid_statistics(
        "blot with defaults",
        output_difference,
        blotted_image,
        template_data,
        20.0,
        16,
    )

    assert med_diff < 1.0e-6
    assert max_diff < 1.0e-5


def test_blot_with_lan3(tmpdir):
    """
    Test do_blot with lan3 grid image
    """
    output_difference = str(tmpdir.join('difference_blot_lan3.txt'))

    input_file = os.path.join(DATA_DIR, 'j8bt06nyq_flt.fits')
    output_template = os.path.join(DATA_DIR, 'reference_blot_lan3.fits')

    outsci = read_image(input_file)
    outsci = make_grid_image(outsci, 64, 100.0)
    outwcs = read_wcs(input_file)
    inwcs = read_wcs(output_template)

    pixmap = utils.calc_pixmap(inwcs, outwcs)

    # compute pscale the old way (only to make
    # tests work with old truth files and thus to show that new API gives
    # same results when equal definitions of the pixel scale is used):
    pscale = np.sqrt(
        np.sum(inwcs.wcs.pc**2, axis=0)[0] /
        np.sum(outwcs.wcs.cd**2, axis=0)[0]
    )

    blotted_image = resample.blot_image(
        outsci,
        pixmap=pixmap,
        pix_ratio=pscale,
        exptime=1.0,
        output_pixel_shape=inwcs.pixel_shape,
        interp="lan3",
    )

    template_data = read_image(output_template)

    _, med_diff, max_diff = centroid_statistics(
        "blot with lan3",
        output_difference,
        blotted_image,
        template_data,
        20.0,
        16,
    )

    assert med_diff < 1.0e-6
    assert max_diff < 1.0e-5


def test_blot_with_lan5(tmpdir):
    """
    Test do_blot with lan5 grid image
    """
    output_difference = str(tmpdir.join('difference_blot_lan5.txt'))

    input_file = os.path.join(DATA_DIR, 'j8bt06nyq_flt.fits')
    output_template = os.path.join(DATA_DIR, 'reference_blot_lan5.fits')

    outsci = read_image(input_file)
    outsci = make_grid_image(outsci, 64, 100.0)
    outwcs = read_wcs(input_file)
    inwcs = read_wcs(output_template)

    pixmap = utils.calc_pixmap(inwcs, outwcs)

    # compute pscale the old way (only to make
    # tests work with old truth files and thus to show that new API gives
    # same results when equal definitions of the pixel scale is used):
    pscale = np.sqrt(
        np.sum(inwcs.wcs.pc**2, axis=0)[0] /
        np.sum(outwcs.wcs.cd**2, axis=0)[0]
    )

    blotted_image = resample.blot_image(
        outsci,
        pixmap=pixmap,
        pix_ratio=pscale,
        exptime=1.0,
        output_pixel_shape=inwcs.pixel_shape,
        interp="lan5",
    )

    template_data = read_image(output_template)

    _, med_diff, max_diff = centroid_statistics(
        "blot with lan5",
        output_difference,
        blotted_image,
        template_data,
        20.0,
        16,
    )

    assert med_diff < 1.0e-6
    assert max_diff < 1.0e-5


def test_context_planes():
    """Reproduce error seen in issue #50"""
    shape = (10, 10)
    output_wcs = wcs.WCS()
    output_wcs.wcs.ctype = ['RA---TAN', 'DEC--TAN']
    output_wcs.wcs.pc = [[1, 0], [0, 1]]
    output_wcs.pixel_shape = shape
    driz = resample.Drizzle(out_shape=tuple(shape))

    image = np.ones(shape)
    inwcs = wcs.WCS()
    inwcs.wcs.ctype = ['RA---TAN', 'DEC--TAN']
    inwcs.wcs.cd = [[1, 0], [0, 1]]
    inwcs.pixel_shape = shape

    pixmap = utils.calc_pixmap(inwcs, output_wcs)

    # context image must be 2D or 3D:
    with pytest.raises(ValueError) as err_info:
        resample.Drizzle(
            kernel='point',
            exptime=0.0,
            out_shape=shape,
            out_ctx=[0, 0, 0],
        )
    assert str(err_info.value).startswith(
        "'out_ctx' must be either a 2D or 3D array."
    )

    driz = resample.Drizzle(
        kernel='square',
        out_shape=output_wcs.array_shape,
        fillval=0.0,
    )

    for i in range(32):
        assert driz.ctx_id == i
        driz.add_image(image, exptime=1.0, pixmap=pixmap)
    assert driz.out_ctx.shape == (1, 10, 10)

    driz.add_image(image, exptime=1.0, pixmap=pixmap)
    assert driz.out_ctx.shape == (2, 10, 10)


def test_no_context_image():
    """Reproduce error seen in issue #50"""
    shape = (10, 10)
    output_wcs = wcs.WCS()
    output_wcs.wcs.ctype = ['RA---TAN', 'DEC--TAN']
    output_wcs.wcs.pc = [[1, 0], [0, 1]]
    output_wcs.pixel_shape = shape
    driz = resample.Drizzle(
        out_shape=tuple(shape),
        begin_ctx_id=-1,
        disable_ctx=True
    )
    assert driz.out_ctx is None
    assert driz.ctx_id is None

    image = np.ones(shape)
    inwcs = wcs.WCS()
    inwcs.wcs.ctype = ['RA---TAN', 'DEC--TAN']
    inwcs.wcs.cd = [[1, 0], [0, 1]]
    inwcs.pixel_shape = shape

    pixmap = utils.calc_pixmap(inwcs, output_wcs)

    for i in range(33):
        driz.add_image(image, exptime=1.0, pixmap=pixmap)
        assert driz.out_ctx is None
        assert driz.ctx_id is None


def test_init_ctx_id():
    # starting context ID must be positive
    with pytest.raises(ValueError) as err_info:
        resample.Drizzle(
            kernel='square',
            exptime=0.0,
            begin_ctx_id=-1,
            out_shape=(10, 10),
        )
    assert str(err_info.value).startswith(
        "Invalid context image ID"
    )

    with pytest.raises(ValueError) as err_info:
        resample.Drizzle(
            kernel='square',
            exptime=0.0,
            out_shape=(10, 10),
            begin_ctx_id=1,
            max_ctx_id=0,
        )
    assert str(err_info.value).startswith(
        "'max_ctx_id' cannot be smaller than 'begin_ctx_id'."
    )


def test_context_agrees_with_weight():
    n = 200
    out_shape = (n, n)

    # allocate output arrays:
    out_img = np.zeros(out_shape, dtype=np.float32)
    out_ctx = np.zeros(out_shape, dtype=np.int32)
    out_wht = np.zeros(out_shape, dtype=np.float32)

    # previous data in weight and context must agree:
    with pytest.raises(ValueError) as err_info:
        out_ctx[0, 0] = 1
        out_ctx[0, 1] = 1
        out_wht[0, 0] = 0.1
        resample.Drizzle(
            kernel='square',
            out_shape=out_shape,
            out_img=out_img,
            out_ctx=out_ctx,
            out_wht=out_wht,
            exptime=1.0,
        )
    assert str(err_info.value).startswith(
        "Inconsistent values of supplied 'out_wht' and 'out_ctx' "
    )


@pytest.mark.parametrize(
    'kernel,fc',
    [
        ('square', True),
        ('point', True),
        ('turbo', True),
        ('lanczos2', False),
        ('lanczos3', False),
        ('gaussian', False),
    ],
)
def test_flux_conservation_nondistorted(kernel, fc):
    n = 200
    in_shape = (n, n)

    # input coordinate grid:
    y, x = np.indices(in_shape, dtype=np.float64)

    # simulate a gaussian "star":
    fwhm = 2.9
    x0 = 50.0
    y0 = 68.0
    sig = fwhm / (2.0 * np.sqrt(2.0 * np.log(2.0 * fwhm)))
    sig2 = sig * sig
    star = np.exp(-0.5 / sig2 * ((x.astype(np.float32) - x0)**2 + (y.astype(np.float32) - y0)**2))
    in_sci = (star / np.sum(star)).astype(np.float32)  # normalize to 1
    in_wht = np.ones(in_shape, dtype=np.float32)

    # linear shift:
    xp = x + 0.5
    yp = y + 0.2

    pixmap = np.dstack([xp, yp])

    out_shape = (int(yp.max()) + 1, int(xp.max()) + 1)
    # make sure distorion is not moving flux out of the image towards negative
    # coordinates (just because of the simple way of how we account for output
    # image size)
    assert np.min(xp) > -0.5 and np.min(yp) > -0.5

    out_img = np.zeros(out_shape, dtype=np.float32)
    out_ctx = np.zeros(out_shape, dtype=np.int32)
    out_wht = np.zeros(out_shape, dtype=np.float32)

    if fc:
        cdrizzle.tdriz(
            in_sci,
            in_wht,
            pixmap,
            out_img,
            out_wht,
            out_ctx,
            pixfrac=1.0,
            scale=1.0,
            kernel=kernel,
            in_units="cps",
            expscale=1.0,
            wtscale=1.0,
        )
    else:
        with pytest.warns(Warning):
            cdrizzle.tdriz(
                in_sci,
                in_wht,
                pixmap,
                out_img,
                out_wht,
                out_ctx,
                pixfrac=1.0,
                scale=1.0,
                kernel=kernel,
                in_units="cps",
                expscale=1.0,
                wtscale=1.0,
            )
        pytest.xfail("Not a flux-conserving kernel")

    assert np.allclose(
        np.sum(out_img * out_wht),
        np.sum(in_sci),
        atol=0.0,
        rtol=0.0001,
    )


@pytest.mark.parametrize(
    'kernel,fc',
    [
        ('square', True),
        ('point', True),
        ('turbo', True),
        ('lanczos2', False),
        ('lanczos3', False),
        ('gaussian', False),
    ],
)
def test_flux_conservation_distorted(kernel, fc):
    n = 200
    in_shape = (n, n)

    # input coordinate grid:
    y, x = np.indices(in_shape, dtype=np.float64)

    # simulate a gaussian "star":
    fwhm = 2.9
    x0 = 50.0
    y0 = 68.0
    sig = fwhm / (2.0 * np.sqrt(2.0 * np.log(2.0 * fwhm)))
    sig2 = sig * sig
    star = np.exp(-0.5 / sig2 * ((x.astype(np.float32) - x0)**2 + (y.astype(np.float32) - y0)**2))
    in_sci = (star / np.sum(star)).astype(np.float32)  # normalize to 1
    in_wht = np.ones(in_shape, dtype=np.float32)

    # linear shift:
    xp = x + 0.5
    yp = y + 0.2
    # add distortion:
    xp += 1e-4 * x**2 + 1e-5 * x * y
    yp += 1e-3 * y**2 - 2e-5 * x * y

    pixmap = np.dstack([xp, yp])

    out_shape = (int(yp.max()) + 1, int(xp.max()) + 1)
    # make sure distorion is not moving (pixels with) flux out of the image
    # towards negative coordinates (just because of the simple way of how we
    # account for output image size):
    assert np.min(xp) > -0.5 and np.min(yp) > -0.5

    out_img = np.zeros(out_shape, dtype=np.float32)
    out_ctx = np.zeros(out_shape, dtype=np.int32)
    out_wht = np.zeros(out_shape, dtype=np.float32)

    if fc:
        cdrizzle.tdriz(
            in_sci,
            in_wht,
            pixmap,
            out_img,
            out_wht,
            out_ctx,
            pixfrac=1.0,
            scale=1.0,
            kernel=kernel,
            in_units="cps",
            expscale=1.0,
            wtscale=1.0,
        )
    else:
        with pytest.warns(Warning):
            cdrizzle.tdriz(
                in_sci,
                in_wht,
                pixmap,
                out_img,
                out_wht,
                out_ctx,
                pixfrac=1.0,
                scale=1.0,
                kernel=kernel,
                in_units="cps",
                expscale=1.0,
                wtscale=1.0,
            )
        pytest.xfail("Not a flux-conserving kernel")

    assert np.allclose(
        np.sum(out_img * out_wht),
        np.sum(in_sci),
        atol=0.0,
        rtol=0.0001,
    )


def test_drizzle_exptime():
    n = 200
    in_shape = (n, n)

    # input coordinate grid:
    y, x = np.indices(in_shape, dtype=np.float64)

    # simulate data:
    in_sci = np.ones(in_shape, dtype=np.float32)
    in_wht = np.ones(in_shape, dtype=np.float32)

    pixmap = np.dstack([x, y])

    # allocate output arrays:
    out_shape = (int(y.max()) + 1, int(x.max()) + 1)
    out_img = np.zeros(out_shape, dtype=np.float32)
    out_ctx = np.zeros(out_shape, dtype=np.int32)
    out_wht = np.zeros(out_shape, dtype=np.float32)

    # starting exposure time must be non-negative:
    with pytest.raises(ValueError) as err_info:
        driz = resample.Drizzle(
            kernel='square',
            out_shape=out_shape,
            fillval="indef",
            exptime=-1.0,
        )
    assert str(err_info.value) == "Exposure time must be non-negative."

    driz = resample.Drizzle(
        kernel='turbo',
        out_shape=out_shape,
        fillval="",
        out_img=out_img,
        out_ctx=out_ctx,
        out_wht=out_wht,
        exptime=1.0,
    )
    assert driz.kernel == 'turbo'

    driz.add_image(in_sci, weight_map=in_wht, exptime=1.03456, pixmap=pixmap)
    assert np.allclose(driz.total_exptime, 2.03456, rtol=0, atol=1.0e-14)

    driz.add_image(in_sci, weight_map=in_wht, exptime=3.1415926, pixmap=pixmap)
    assert np.allclose(driz.total_exptime, 5.1761526, rtol=0, atol=1.0e-14)

    with pytest.raises(ValueError) as err_info:
        driz.add_image(in_sci, weight_map=in_wht, exptime=-1, pixmap=pixmap)
    assert str(err_info.value) == "'exptime' *must* be a strictly positive number."

    # exptime cannot be 0 when output data has data:
    with pytest.raises(ValueError) as err_info:
        out_ctx[0, 0] = 1
        driz = resample.Drizzle(
            kernel='square',
            out_shape=out_shape,
            fillval="indef",
            out_img=out_img,
            out_ctx=out_ctx,
            out_wht=out_wht,
            exptime=0.0,
        )
    assert str(err_info.value).startswith(
        "Inconsistent exposure time and context and/or weight images:"
    )

    # exptime must be 0 when output arrays are not provided:
    with pytest.raises(ValueError) as err_info:
        driz = resample.Drizzle(
            kernel='square',
            out_shape=out_shape,
            exptime=1.0,
        )
    assert str(err_info.value).startswith(
        "Exposure time must be 0.0 for the first resampling"
    )


def test_drizzle_unsupported_kernel():
    with pytest.raises(ValueError) as err_info:
        resample.Drizzle(
            kernel='magic_image_improver',
            out_shape=(10, 10),
            exptime=0.0,
        )
    assert str(err_info.value) == "Kernel 'magic_image_improver' is not supported."


def test_pixmap_shape_matches_image():
    n = 200
    in_shape = (n, n)

    # input coordinate grid:
    y, x = np.indices((n + 1, n), dtype=np.float64)

    # simulate data:
    in_sci = np.ones(in_shape, dtype=np.float32)
    in_wht = np.ones(in_shape, dtype=np.float32)

    pixmap = np.dstack([x, y])

    driz = resample.Drizzle(
        kernel='square',
        fillval=0.0,
        exptime=0.0,
    )

    # last two sizes of the pixelmap must match those of input images:
    with pytest.raises(ValueError) as err_info:
        driz.add_image(
            in_sci,
            exptime=1.0,
            pixmap=pixmap,
            weight_map=in_wht,
        )
    assert str(err_info.value) == "'pixmap' shape is not consistent with 'data' shape."


def test_drizzle_fillval():
    n = 200
    in_shape = (n, n)

    # input coordinate grid:
    y, x = np.indices(in_shape, dtype=np.float64)

    # simulate a gaussian "star":
    fwhm = 2.9
    x0 = 50.0
    y0 = 68.0
    sig = fwhm / (2.0 * np.sqrt(2.0 * np.log(2.0 * fwhm)))
    sig2 = sig * sig
    star = np.exp(-0.5 / sig2 * ((x.astype(np.float32) - x0)**2 + (y.astype(np.float32) - y0)**2))
    in_sci = (star / np.sum(star)).astype(np.float32)  # normalize to 1
    in_wht = np.zeros(in_shape, dtype=np.float32)
    mask = np.where((x.astype(np.float32) - x0)**2 + (y.astype(np.float32) - y0)**2 <= 10)
    in_wht[mask] = 1.0

    # linear shift:
    xp = x + 50
    yp = y + 50

    pixmap = np.dstack([xp, yp])

    out_shape = (int(yp.max()) + 1, int(xp.max()) + 1)
    # make sure distorion is not moving flux out of the image towards negative
    # coordinates (just because of the simple way of how we account for output
    # image size)
    assert np.min(xp) > -0.5 and np.min(yp) > -0.5

    out_img = np.zeros(out_shape, dtype=np.float32) - 1.11
    out_ctx = np.zeros((1, ) + out_shape, dtype=np.int32)
    out_wht = np.zeros(out_shape, dtype=np.float32)

    driz = resample.Drizzle(
        kernel='square',
        out_shape=out_shape,
        fillval="indef",
        exptime=0.0,
    )

    driz.add_image(in_sci, weight_map=in_wht, exptime=1.0, pixmap=pixmap)
    assert np.isnan(driz.out_img[0, 0])
    assert driz.out_img[int(y0) + 50, int(x0) + 50] > 0.0

    driz = resample.Drizzle(
        kernel='square',
        out_shape=out_shape,
        fillval="-1.11",
        out_img=out_img.copy(),
        out_ctx=out_ctx.copy(),
        out_wht=out_wht.copy(),
        exptime=0.0,
    )
    driz.add_image(in_sci, weight_map=in_wht, exptime=1.0, pixmap=pixmap)
    assert np.allclose(driz.out_img[0, 0], -1.11, rtol=0.0, atol=1.0e-7)
    assert driz.out_img[int(y0) + 50, int(x0) + 50] > 0.0
    assert set(driz.out_ctx.ravel().tolist()) == {0, 1}

    # test same with numeric fillval:
    driz = resample.Drizzle(
        kernel='square',
        out_shape=out_shape,
        fillval=-1.11,
        out_img=out_img.copy(),
        out_ctx=out_ctx.copy(),
        out_wht=out_wht.copy(),
        exptime=0.0,
    )
    driz.add_image(in_sci, weight_map=in_wht, exptime=1.0, pixmap=pixmap)
    assert np.allclose(driz.out_img[0, 0], -1.11, rtol=0.0, atol=1.0e-7)
    assert np.allclose(float(driz.fillval), -1.11, rtol=0.0, atol=np.finfo(float).eps)

    # make sure code raises exception for unsuported fillval:
    with pytest.raises(ValueError) as err_info:
        resample.Drizzle(
            kernel='square',
            out_shape=out_shape,
            fillval="fillval",
            exptime=0.0,
        )
    assert str(err_info.value) == "could not convert string to float: 'fillval'"


def test_resample_get_shape_from_pixmap():
    n = 200
    in_shape = (n, n)

    # input coordinate grid:
    y, x = np.indices(in_shape, dtype=np.float64)

    # simulate constant data:
    in_sci = np.ones(in_shape, dtype=np.float32)
    in_wht = np.ones(in_shape, dtype=np.float32)

    pixmap = np.dstack([x, y])

    driz = resample.Drizzle(
        kernel='point',
        exptime=0.0,
    )

    driz.add_image(in_sci, weight_map=in_wht, exptime=1.0, pixmap=pixmap)
    assert driz.out_img.shape == in_shape


def test_resample_counts_units():
    n = 200
    in_shape = (n, n)

    # input coordinate grid:
    y, x = np.indices(in_shape, dtype=np.float64)
    pixmap = np.dstack([x, y])

    # simulate constant data:
    in_sci = np.ones(in_shape, dtype=np.float32)
    in_wht = np.ones(in_shape, dtype=np.float32)

    driz = resample.Drizzle()
    driz.add_image(in_sci, weight_map=in_wht, exptime=1.0, pixmap=pixmap, in_units='cps')
    cps_max_val = driz.out_img.max()

    driz = resample.Drizzle()
    driz.add_image(in_sci, weight_map=in_wht, exptime=2.0, pixmap=pixmap, in_units='counts')
    counts_max_val = driz.out_img.max()

    assert abs(counts_max_val - cps_max_val / 2.0) < 1.0e-14


def test_resample_inconsistent_output():
    n = 200
    out_shape = (n, n)

    # different shapes:
    out_img = np.zeros((n, n), dtype=np.float32)
    out_ctx = np.zeros((1, n, n + 1), dtype=np.int32)
    out_wht = np.zeros((n + 1, n + 1), dtype=np.float32)

    # shape from out_img:
    driz = resample.Drizzle(
        kernel='point',
        exptime=0.0,
        out_img=out_img,
    )
    assert driz.out_img.shape == out_shape

    # inconsistent shapes:
    out_shape = (n + 1, n)
    with pytest.raises(ValueError) as err_info:
        resample.Drizzle(
            kernel='point',
            exptime=0.0,
            out_shape=out_shape,
            out_img=out_img,
            out_ctx=out_ctx,
            out_wht=out_wht,
        )
    assert str(err_info.value).startswith("Inconsistent data shapes specified")