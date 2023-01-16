"""Convert blocks to svg file.

"""

import logging
import math
import string

from dataclasses import dataclass

from . import read_blocks

from .scene_stream import (
    Block,
    RootTextBlock,
    AuthorIdsBlock,
    MigrationInfoBlock,
    PageInfoBlock,
    SceneTreeBlock,
    TreeNodeBlock,
    SceneGroupItemBlock,
    SceneLineItemBlock,
)

from .writing_tools import (
    Pen,
)

_logger = logging.getLogger(__name__)


SCREEN_WIDTH = 1404
SCREEN_HEIGHT = 1872

SVG_HEADER = string.Template("""
<svg xmlns="http://www.w3.org/2000/svg" height="$height" width="$width">
    <script type="application/ecmascript"> <![CDATA[
        var visiblePage = 'p1';
        function goToPage(page) {
            document.getElementById(visiblePage).setAttribute('style', 'display: none');
            document.getElementById(page).setAttribute('style', 'display: inline');
            visiblePage = page;
        }
    ]]>
    </script>
""")


@dataclass
class SvgDocInfo:
    height: int
    width: int
    xpos_delta: float
    ypos_delta: float


def rm2svg(infile, outfile):
    # we need to process the blocks twice to understand the dimensions, so
    # let's put the iterable into a list
    blocks = list(read_blocks(infile))

    # get document dimensions
    svg_doc_info = get_dimensions(blocks)

    with open(outfile, 'w') as output:
        # add svg header
        output.write(SVG_HEADER.substitute(height=svg_doc_info.height, width=svg_doc_info.width))
        output.write('\n')

        # add svg page info
        output.write('    <g id="p1" style="display:inline">\n')
        output.write('        <filter id="blurMe"><feGaussianBlur in="SourceGraphic" stdDeviation="10" /></filter>\n')

        for block in blocks:
            if isinstance(block, SceneLineItemBlock):
                draw_stroke(block, output, svg_doc_info)
            else:
                print(f'warning: not converting block: {block.__class__}')

        # Overlay the page with a clickable rect to flip pages
        output.write('\n')
        output.write('        <!-- clickable rect to flip pages -->\n')
        output.write(f'        <rect x="0" y="0" width="{svg_doc_info.width}" height="{svg_doc_info.height}" fill-opacity="0"/>\n')
        # Closing page group
        output.write('    </g>\n')
        # END notebook
        output.write('</svg>\n')
        output.close()


def draw_stroke(block, output, svg_doc_info):
    print('----SceneLineItemBlock')
    # a SceneLineItemBlock contains a stroke
    output.write(f'        <!-- SceneLineItemBlock item_id: {block.item_id} -->\n')
    # make sure the object is not empty
    if block.value is None:
        return

    # initiate the pen
    pen = Pen.create(block.value.tool.value, block.value.color.value, block.value.thickness_scale)

    # BEGIN stroke
    output.write('        <polyline ')
    output.write(f'style="fill:none;stroke:{pen.stroke_color};stroke-width:{pen.stroke_width};opacity:{pen.stroke_opacity}" ')
    output.write(f'stroke-linecap="{pen.stroke_linecap}" ')
    output.write('points="')

    last_xpos = -1.
    last_ypos = -1.
    last_segment_width = 0
    # Iterate through the point to form a polyline
    for point_id, point in enumerate(block.value.points):
        # align the original position
        xpos = point.x + svg_doc_info.xpos_delta
        ypos = point.y + svg_doc_info.ypos_delta
        # stretch the original position
        # ratio = (svg_doc_info.height / svg_doc_info.width) / (1872 / 1404)
        # if ratio > 1:
        #    xpos = ratio * ((xpos * svg_doc_info.width) / 1404)
        #    ypos = (ypos * svg_doc_info.height) / 1872
        # else:
        #    xpos = (xpos * svg_doc_info.width) / 1404
        #    ypos = (1 / ratio) * (ypos * svg_doc_info.height) / 1872
        # process segment-origination points
        if point_id % pen.segment_length == 0:
            tilt = point.direction  # XXX
            segment_color = pen.get_segment_color(point.speed, tilt, point.width, point.pressure, last_segment_width)
            segment_width = pen.get_segment_width(point.speed, tilt, point.width, point.pressure, last_segment_width)
            segment_opacity = pen.get_segment_opacity(point.speed, tilt, point.width, point.pressure, last_segment_width)
            # print(segment_color, segment_width, segment_opacity, pen.stroke_linecap)
            # UPDATE stroke
            output.write('"/>\n')
            output.write('        <polyline ')
            output.write(f'style="fill:none; stroke:{segment_color} ;stroke-width:{segment_width:.3f};opacity:{segment_opacity}" ')
            output.write(f'stroke-linecap="{pen.stroke_linecap}" ')
            output.write('points="')
            if last_xpos != -1.:
                # Join to previous segment
                output.write(f'{last_xpos:.3f},{last_ypos:.3f} ')
        # store the last position
        last_xpos = xpos
        last_ypos = ypos
        last_segment_width = segment_width

        # BEGIN and END polyline segment
        output.write(f'{xpos:.3f},{ypos:.3f} ')

    # END stroke
    output.write('" />\n')


def get_limits(blocks):
    xmin = xmax = None
    ymin = ymax = None
    for block in blocks:
        if isinstance(block, SceneLineItemBlock):
            xmin_tmp, xmax_tmp, ymin_tmp, ymax_tmp = get_limits_stroke(block)
        else:
            continue
        if xmin_tmp is None:
            continue
        if xmin is None or xmin > xmin_tmp:
            xmin = xmin_tmp
        if xmax is None or xmax < xmax_tmp:
            xmax = xmax_tmp
        if ymin is None or ymin > ymin_tmp:
            ymin = ymin_tmp
        if ymax is None or ymax < ymax_tmp:
            ymax = ymax_tmp
    return xmin, xmax, ymin, ymax


def get_limits_stroke(block):
    # make sure the object is not empty
    if block.value is None:
        return None, None, None, None
    xmin = xmax = None
    ymin = ymax = None
    for point in block.value.points:
        xpos, ypos = point.x, point.y
        if xmin is None or xmin > xpos:
            xmin = xpos
        if xmax is None or xmax < xpos:
            xmax = xpos
        if ymin is None or ymin > ypos:
            ymin = ypos
        if ymax is None or ymax < ypos:
            ymax = ypos
    return xmin, xmax, ymin, ymax


def get_dimensions(blocks):
    # get block limits
    xmin, xmax, ymin, ymax = get_limits(blocks)
    # {xpos,ypos} coordinates are based on the center of the top of the
    # doc
    xpos_delta = max(SCREEN_WIDTH / 2, -xmin if xmin is not None else 0)
    ypos_delta = 0
    # adjust dimensions if needed
    width = int(math.ceil(max(SCREEN_WIDTH, xmax - xmin if xmin is not None and xmax is not None else 0)))
    height = int(math.ceil(max(SCREEN_HEIGHT, ymax - ymin if ymin is not None and ymax is not None else 0)))
    # print(f"xmin: {xmin} xmax: {xmax} ymin: {ymin} ymax: {ymax}")
    # print(f"height: {height} width: {width} xpos_delta: {xpos_delta} ypos_delta: {ypos_delta}")
    return SvgDocInfo(height=height, width=width, xpos_delta=xpos_delta, ypos_delta=0)