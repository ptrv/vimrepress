#!/bin/bash


TEMP_DIR=/tmp/vimpress_relase
hg archive $TEMP_DIR
cd $TEMP_DIR/plugin
(sed 's/^python.\+$/python << EOF/' blog-dev.vim; cat blog.py) > blog.vim
VER=`grep Version blog.vim|awk '{print $3}'`
RELEASE_FILE=/tmp/vimpress_$VER.zip
cd $TEMP_DIR
zip -x '.hgtags' -x '.hg_archival.txt' -x release_vimpress.sh -x plugin/blog.py -x plugin/blog-dev.vim -r $RELEASE_FILE .

echo $RELEASE_FILE


