======================
NOTE: WORK IN PROGRESS
======================

This document needs to be updated to remove nova-specific references, and to
include hacking rules as we determine they are needed.


Building Docs
-------------
Normal Sphinx docs can be built via the setuptools ``build_sphinx`` command. To
do this via ``tox``, simply run ``tox -e docs``,
which will cause a virtualenv with all of the needed dependencies to be
created and then inside of the virtualenv, the docs will be created and
put into doc/build/html.

Building a PDF of the Documentation
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
If you'd like a PDF of the documentation, you'll need LaTeX and ImageMagick
installed, and additionally some fonts. On Ubuntu systems, you can get what you
need with::

    apt-get install texlive-full imagemagick

Then you can use the ``build_latex_pdf.sh`` script in tools/ to take care
of both the sphinx latex generation and the latex compilation. For example::

    tools/build_latex_pdf.sh

The script must be run from the root of the Placement repository and it will
copy the output pdf to Placement.pdf in that directory.
