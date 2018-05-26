#! usr/bin/python_2
"""
    Source:
    29.04.2018 Steve Theodore on github
    https://gist.github.com/theodox/0d65255f0959cf8a8fcc64d3e39fc15f#file-canvas-py

    MIT License

    Copyright (c) 2018 Stefan Tapper

    Permission is hereby granted, free of charge, to any person obtaining a copy
    of this software and associated documentation files (the "Software"), to deal
    in the Software without restriction, including without limitation the rights
    to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the Software is
    furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all
    copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
    SOFTWARE.

"""
from array import array
from itertools import islice, izip, imap, izip_longest, tee, chain, product, ifilter

from maya.api.OpenMaya import MImage

import ctypes


def image_to_bytearray(img):
    """
    convert an api2 MImage to a python bytearray
    """
    w, h = img.getSize()
    data_ptr = ctypes.cast(img.pixels(), ctypes.POINTER(ctypes.c_char))
    return array('B', ctypes.string_at(data_ptr, w * h * 4))


def image_to_floatarray(img):
    """
    convert an api2 MImage in float format to a python bytearray
    """
    return array('f', map(lambda p: p / 255.0, image_to_bytearray(img)))


def region_product(xmin, ymin, xmax, ymax):
    """
    yield all the addresses in the range (xmin, ymin) to  (xmax, ymax) in row-first order
    """
    cols = xrange(xmin, xmax)
    rows = xrange(ymin, ymax)
    return product(cols, rows)


def pixel_pipe(source, target, offset=(0, 0), region=None):
    """
    map pixels from Canvas <source> to Canvas <target>,
        offset sets the start location (defaults to 0,0)
        region copies only the specified region of the SOURCE

    Any target addresses that fall outside the bounds of <target> are ignored
    """
    if region is None:
        region = source.bounds()
    source_pixels = region_product(*region)
    target_pixels = region_product(region[0] + offset[0],
                                   region[1] + offset[1],
                                   region[2] + offset[0],
                                   region[3] + offset[1])
    valid = lambda val: val[0] in source and val[1] in target
    return ifilter(valid, izip(source_pixels, target_pixels))


def copy_pixels(source, target, offset=(0, 0), region=None):
    """
    copy  pixels from Canvas <source> to Canvas <target>,
        offset sets the start location (defaults to 0,0)
        region copies only the specified region of the SOURCE
    all copies are contiguous.  Any addresses that fall outside the bounds of <target> are ignored
    """
    for src, tgt in pixel_pipe(source, target, offset, region):
        target[tgt] = source[src]


def apply_pixels(operation, source, target, offset=(0, 0), region=None):
    """
    copy pixels from <source> to <target>, like copy_pixels, but calls <operation> on each pair of sourc and target
    pixels to set the final value.  EG:

        apply_pixels(operator.add, source, target)

    would add the source image to the target image.  Most of these operations will be in the pixelops namespace:

        import pixelops

        red_filter = pixelops.ChannelMixer.red
        apply_pixels(red_filter, source, target)



    """
    assert callable(operation)
    for src, tgt in pixel_pipe(source, target, offset, region):
        target[tgt] = operation(target[tgt], source[src])


def filter_pixels(operation, target, region=None):
    """
    applies a single-argument callable to every pixel in the target. If an optional region is supplied,
    only operate in that region
    """
    region = region or target.bounds()
    for pixel in region_product(*region):
        target[pixel] = operation(target[pixel])


class Canvas(object):
    """
    Represents a bitmap that can be edited in memory.  Typically used for working with pixel data that comes from an
    api2.MImage.

    Example usage:

        canvas = Canvas.from_file(r"path/to/file")
        print canvas
        # < Canvas (128 x 128 x 4) @ 1237854 >

        # get a pixel value
        print canvas[32, 32]
        # (127, 64, 0, 255)

        # set a pixel value
        canvas [32, 23] = (0,0,0,0)

        # create a blank canvas
        c2 = canvas.new(64, 64)

        # fill it with red
        c2.fill( (255, 0, 0 255) )

        # convert to MImage

        c2.as_image()


    """

    class Formats:
        TGA = 'tga'
        TIFF = 'tiff'
        PNG = 'png'

    ARRAY_TYPE = 'B'

    def __init__(self, data, width, height, depth=4):
        self.width = width
        self.height = height
        self.depth = depth
        i = tee(data, self.depth)
        iterators = (islice(i[n], n, None, self.depth) for n in range(self.depth))
        self.channels = [array(self.ARRAY_TYPE, b) for b in iterators]

    def __getitem__(self, index):
        assert index in self
        x, y = index
        address = x + (y * self.width)
        return tuple(channel[address] for channel in self.channels)

    def __setitem__(self, index, val):
        assert index in self
        x, y = index
        address = x + (y * self.width)

        for component, channel in zip(val, self.channels):
            channel[address] = component

    def bytes(self):
        """
        Returns the byte values of this image in the same interlaved order as an MImage
        """
        return chain(*izip(*self.channels))

    def values(self):
        """
        returns a flat array of all the pixel values in this image as a RGBA tuples, row-first order
        """
        return imap(self.__getitem__, self.addresses())

    def __repr__(self):
        return "< {0} ({1} x {2} x {3}) @  {4}>".format(self.__class__.__name__, self.width, self.height, self.depth,
                                                        id(self))

    def __contains__(self, address):
        x, y = address
        return (not x < 0) and x < self.width and (not y < 0) and y < self.height

    def __len__(self):
        return len(self.channels[0])

    def as_image(self):
        """
        Return the contents of this object as an MImage
        """
        new_image = MImage()
        new_image.setPixels(bytearray(self.bytes()), self.width, self.height)
        return new_image

    def to_file(self, path, filetype=Formats.TGA):
        """
        save this Canvas to disk, with the supplied format or TGA if non is supplied
        """
        img = self.as_image()
        img.writeToFile(path, outputFormat=filetype)

    def resized(self, new_width, new_height, preserve_aspect=True):
        """
        returns a new Canvas resized to <new_width, new_height>.

        Note uses an MImage under the hood
        """
        new_img = self.as_image()
        new_img.resize(new_width, new_height, preserve_aspect)
        return self.__class__.from_image(new_img)

    @classmethod
    def from_image(cls, img):
        """
        Creates a Canvas from an api2 MImage
        """
        w, h = img.getSize()
        data = image_to_bytearray(img)
        return cls(data, w, h)

    @classmethod
    def from_file(cls, path):
        """
        Creates a canvas from a disk file. Supports the same formats as MImage.readFromFile()
        """
        img = MImage()
        img.readFromFile(path)
        return cls.from_image(img)

    @classmethod
    def new(cls, width, height, depth=4):
        """
        Creates a new Canvas of size <width, height> with <depth> channels (defaults to 4)
        """
        dummy_data = array(cls.ARRAY_TYPE, [0] * width * height * depth)
        return cls(dummy_data, width, height, depth)

    def addresses(self):
        """
        returns all of the valid pixel addresses in this Canvas as a generator
        """
        return region_product(0, 0, self.width, self.height)

    def bounds(self):
        """
        returns the size of this Canvas as (0, 0, width, height)
        """
        return 0, 0, self.width, self.height

    def fill(self, val, region=None):
        """
        fill all or part of this canvas with color <val>.  if <region> is specified as a range (min_x, min_y, max_x,
        max_y) the fill is limited to that region
        """
        assert len(val) == self.depth
        region = region or self.bounds()

        for x, y in region_product(*region):
            address = x + (y * self.width)
            for ch, vv in izip_longest(self.channels, val):
                ch[address] = vv


class FloatCanvas(Canvas):
    ARRAY_TYPE = 'f'

    def bytes(self):
        float_vals = super(FloatCanvas, self).bytes()
        return imap(lambda v: int(round(v * 255, 0)), float_vals)

    @classmethod
    def from_image(cls, img):
        w, h = img.getSize()
        data = image_to_floatarray(img)
        return cls(data, w, h)


if __name__ == '__main__':

    def run_tests():
        def test_region_product():
            values = list(region_product(0, 0, 32, 16))
            assert values[0] == (0, 0)
            assert values[-1] == (31, 15)

        def test_peek():
            t = Canvas.new(4, 4)
            assert t[0, 0] == (0, 0, 0, 0)
            for c in t.channels:
                c[5] = 1
                c[1] = 1
            assert t[1, 1] == t[1, 0] == (1, 1, 1, 1)

        def test_poke():
            t = Canvas.new(4, 4)
            t[1, 2] = (1, 2, 3, 4)
            assert t[1, 2] == (1, 2, 3, 4)
            t = Canvas.new(4, 2, depth=3)
            t[3, 0] = (1, 2, 3)
            assert t[3, 0] == (1, 2, 3)
            t[1, 1] = (1, 2, 3)
            assert t[1, 1] == (1, 2, 3)

        def test_new():
            t = Canvas.new(7, 3)
            assert t.width == 7
            assert t.height == 3

        def test_bounds():
            t = Canvas.new(11, 12)
            assert t.bounds() == (0, 0, 11, 12)

        def test_bytes():
            t1 = Canvas.new(4, 4)
            assert str(bytearray(t1.bytes())) == '\x00' * 64

            t1 = Canvas.new(4, 4, depth=3)
            assert str(bytearray(t1.bytes())) == '\x00' * 48

        def test_addresses():
            t1 = Canvas.new(4, 4)
            expected = [(x, y) for x in range(4) for y in range(4)]
            assert list(t1.addresses()) == expected

        def test_contains():
            t1 = Canvas.new(4, 4)
            assert (0, 0) in t1
            assert (3, 3) in t1
            assert (1, 2) in t1
            assert not (4, 2) in t1
            assert not (2, 4) in t1
            assert not (-1, 0) in t1
            assert not (1, -1) in t1
            assert not (-1, 4) in t1

        def test_fill():
            t1 = Canvas.new(4, 4)
            t1.fill((255, 128, 0, 255))
            for ad in t1.addresses():
                assert t1[ad] == (255, 128, 0, 255)

        def test_fill_region():
            t1 = Canvas.new(4, 4)
            t1.fill((255, 128, 0, 255), region=(1, 1, 3, 3))
            assert t1[0, 0] == t1[3, 3] == t1[0, 3] == t1[3, 0] == (0, 0, 0, 0)
            assert t1[1, 1] == t1[2, 2] == t1[1, 2] == t1[2, 1] == (255, 128, 0, 255)

        def test_values():
            t1 = Canvas.new(4, 4)
            t1[0, 0] = (1, 2, 3, 4)
            t1[1, 1] = (5, 6, 7, 8)
            t1[2, 2] = (9, 10, 11, 12)
            t1[3, 3] = (13, 14, 15, 16)
            assert list(t1.values()) == [(1, 2, 3, 4), (0, 0, 0, 0), (0, 0, 0, 0), (0, 0, 0, 0), (0, 0, 0, 0),
                                         (5, 6, 7, 8),
                                         (0, 0, 0, 0), (0, 0, 0, 0), (0, 0, 0, 0), (0, 0, 0, 0), (9, 10, 11, 12),
                                         (0, 0, 0, 0),
                                         (0, 0, 0, 0), (0, 0, 0, 0), (0, 0, 0, 0), (13, 14, 15, 16)]
            assert list(t1.bytes()) == list(chain.from_iterable(t1.values()))

        def test_copy():
            source = Canvas.new(4, 4)
            source.fill((0, 64, 128, 255))
            source[0, 0] = (0, 0, 0, 0)
            source[3, 1] = (0, 0, 0, 0)

            tgt = Canvas.new(2, 2)
            copy_pixels(source, tgt, (0, 0))
            assert tgt[0, 0] == (0, 0, 0, 0)

            tgt = Canvas.new(2, 2)
            copy_pixels(source, tgt, (1, 1))
            assert tgt[0, 0] == tgt[1, 0] == tgt[0, 1] == (0, 0, 0, 0)

            tgt = Canvas.new(2, 2)
            copy_pixels(source, tgt, (-2, -2))
            assert not (0, 0, 0, 0) in list(tgt.values())

            source = Canvas.new(4, 6)
            source.fill((255, 0, 0, 0))
            target = Canvas.new(3, 2)
            copy_pixels(source, target, (1, 1))

        def test_pixel_pipe_symmetrical():
            source = Canvas.new(4, 4)
            target = Canvas.new(4, 4)
            for a, b in (pixel_pipe(source, target)):
                assert (a == b)

        def test_pixel_pipe_offset():
            source = Canvas.new(4, 4)
            target = Canvas.new(4, 4)
            for a, b in (pixel_pipe(source, target, offset=(2, 2))):
                assert (b == (a[0] + 2, a[1] + 2))

        test_region_product()
        test_peek()
        test_poke()
        test_new()
        test_bounds()
        test_bytes()
        test_fill()
        test_addresses()
        test_fill_region()
        test_values()
        test_contains()
        test_copy()
        test_pixel_pipe_symmetrical()
        test_pixel_pipe_offset()


    run_tests()
