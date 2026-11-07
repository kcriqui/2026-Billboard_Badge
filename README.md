![Billboard_Badge](assets/frame_graphic_demo.png "2026 Hackaday Supercon Billboard Badge")

# Badge Hardware
The badge uses a 9.7 inch Pervasive Displays E2969JS0B1 electronic paper panel that was recycled from price tags which were destined for a now bankrupt German department store chain, coupled with an ESP32-S3 microcontroller.

## Pins

The board only has two truly free GPIOs

* GPIO9
* GPIO41

The SAO ports, however, have many possibilities

* SAO1: GPIO2 and GPIO42
* SAO2: GPIO4 and GPIO5
* SAO3: GPIO7 and GPIO6
* I2C bus: SDA on GPIO17 and SCL on GPIO18

The row of WS2812-compatible LEDs is on GPIO38

## Buttons

* Menu +/-: GPIO40 / GPIO15
* User A/B: GPIO39 / GPIO15

# Applications
In its out of the box configuration the badge can show the 2026 Supercon schedule, act as a digital name tag, and cycle through a built-in collection of art from Hackaday's incredible Art Director Joe Kim. If you come up with additional apps that you'd like to share, feel free to make a pull request.

# Displaying Images

The badge's display only supports three colors: white, black, red. Shading between those needs to be implemented by dithering pixels of those colors together. Unlike LCD, CRT, or other displays you may be used to, you cannot set multiple colors within a single pixel, each pixel is only one of the three colors.

The badge firmware picks a color for each pixel based on this logic:
- If the red value is >50% and blue and green are both <50%, then the pixel will be red.
- If the red, green, and blue values of the pixel are all <50%, then the pixel will be black.
- Otherwise the pixel will be white.

Additionally, since the display is so large, loading large images can easily run out of memory. Therefore, it is best to compress each image down to a limited color space before placing on the badge. This is easily done with [ImageMagick](https://imagemagick.org/), namely with the command `magick oldfile.png -remap scripts/palette.gif newfile.png`. This reduces the image down to a colorspace that only supports 3 colors, which are white, black, and red.

Based on the above pixel logic, where each pixel is already one of the three supported colors, it's easy to see how the image will be displayed. Luckily, but converting the image on your computer, you can see what it will look like before rendering it on the badge.

# Credits (Kevin's fork)

- **Long Exposure Earth** app (`firmware/badge/apps/earth.py`): Made with [Natural Earth](https://www.naturalearthdata.com). Free vector and raster map data @ naturalearthdata.com (public domain); the red world map `firmware/badge/data/earth/world.png` is rendered from `ne_110m_land` by `tools/make_world_map.py`. Live data: ISS position from [wheretheiss.at](https://wheretheiss.at), earthquakes from the [USGS Earthquake Hazards Program](https://earthquake.usgs.gov/earthquakes/feed/).
- **Space Weather** app (`firmware/badge/apps/spaceweather.py`): live data from the [NOAA Space Weather Prediction Center](https://www.swpc.noaa.gov) (solar wind speed and magnetic field summaries, estimated planetary Kp, NOAA G-scale).
- **XKCD** app: comics by Randall Munroe, [xkcd.com](https://xkcd.com) (CC BY-NC 2.5), fetched live; not redistributed here.
- **Nametag** handwriting: [xkcd Script](https://github.com/ipython/xkcd-font) font (CC BY-NC 3.0), used to render the name tag image; the font itself is not committed.
- Fast refresh ported from upstream PR #3 (FacioErgoSum); faster display driver merged from upstream PR #4 (trandi).
