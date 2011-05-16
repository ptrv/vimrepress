#!/bin/bash


cd plugin
(sed 's/^python.\+$/python << EOF/' blog-dev.vim; cat blog.py) > blog.vim
VER=`grep Version blog.vim|awk '{print $3}'`
RELEASE_FILE=/tmp/vimpress_$VER.zip
hg archive -X plugin/blog-dev.vim -X plugin/blog.py $RELEASE_FILE

echo $RELEASE_FILE


