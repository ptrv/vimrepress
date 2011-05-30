#!/bin/bash


TEMP_DIR=/tmp/vimpress_relase
REV=`hg log -r tip|grep -e "^changeset"|awk '{print $2}'|tr ':' '_'`
hg archive $TEMP_DIR
cd $TEMP_DIR/plugin
(sed 's/^python.\+$/python << EOF/' blog-dev.vim; cat blog.py) > blog.vim
VER=`grep Version blog.vim|awk '{print $3}'`
RELEASE_FILE="/tmp/vimpress_"$VER"_r"$REV".zip"
cd $TEMP_DIR
if [[ -f $RELEASE_FILE ]]; then rm $RELEASE_FILE; fi
zip -x '.hgtags' -x '.hg_archival.txt' -x release_vimpress.sh -x plugin/blog.py -x plugin/blog-dev.vim -r $RELEASE_FILE .

rm -rf $TEMP_DIR
echo $RELEASE_FILE


