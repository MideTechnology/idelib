from io import BytesIO, StringIO

FILES = [('./testing/SSX70065.IDE', 'rb'),
         ('./testing/SSX66115.IDE', 'rb'),
         ('./test.ide', 'rb'),
         ('./testing/SSX_Data.IDE', 'rb'),
         ('./testing/with_userdata.IDE', 'rb')]
FILE_DICT = {}

for fName, mode in FILES:
    with open(fName, mode) as f:
        FILE_DICT[fName] = (f.read(), mode)


def makeStreamLike(fName):
    dat, mode = FILE_DICT[fName]
    if 'b' in mode:
        streamType = BytesIO
    else:
        streamType = StringIO
    stream = streamType(dat)
    stream.name = fName
    return stream
