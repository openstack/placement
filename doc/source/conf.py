# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
#
#  placement documentation build configuration file
#
# Refer to the Sphinx documentation for advice on configuring this file:
#
#   http://www.sphinx-doc.org/en/stable/config.html

import os
import sys

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
sys.path.insert(0, os.path.abspath('../../'))
sys.path.insert(0, os.path.abspath('../'))
sys.path.insert(0, os.path.abspath('./'))

# -- General configuration ----------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom ones.

# TODO(efried): Trim this moar
extensions = ['sphinx.ext.autodoc',
              'sphinx.ext.todo',
              'openstackdocstheme',
              'sphinx.ext.coverage',
              'sphinx.ext.graphviz',
              'sphinx_feature_classification.support_matrix',
              'oslo_config.sphinxconfiggen',
              'oslo_config.sphinxext',
              'oslo_policy.sphinxpolicygen',
              'oslo_policy.sphinxext',
              'sphinxcontrib.actdiag',
              'sphinxcontrib.seqdiag',
              ]

# openstackdocstheme options
openstackdocs_repo_name = 'openstack/placement'
openstackdocs_pdf_link = True
openstackdocs_use_storyboard = True

config_generator_config_file = '../../etc/placement/config-generator.conf'
sample_config_basename = '_static/placement'

policy_generator_config_file = [
    ('../../etc/placement/policy-generator.conf',
     '_static/placement')
]

actdiag_html_image_format = 'SVG'
actdiag_antialias = True

seqdiag_html_image_format = 'SVG'
seqdiag_antialias = True

todo_include_todos = True

# The suffix of source filenames.
source_suffix = '.rst'

# The master toctree document.
master_doc = 'index'

# General information about the project.
copyright = '2010-present, OpenStack Foundation'

# If true, the current module name will be prepended to all description
# unit titles (such as .. function::).
add_module_names = False

# If true, sectionauthor and moduleauthor directives will be shown in the
# output. They are ignored by default.
show_authors = False

# The name of the Pygments (syntax highlighting) style to use.
pygments_style = 'native'

# A list of ignored prefixes for module index sorting.
modindex_common_prefix = ['placement.']

# -- Options for HTML output --------------------------------------------------

# The theme to use for HTML and HTML Help pages.  Major themes that come with
# Sphinx are currently 'default' and 'sphinxdoc'.
html_theme = 'openstackdocs'

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ['_static']
html_extra_path = ['_extra']

# -- Options for LaTeX output -------------------------------------------------

# Grouping the document tree into LaTeX files. List of tuples
# (source start file, target name, title, author, documentclass
# [howto/manual]).
latex_documents = [
    ('index', 'doc-placement.tex', 'Placement Documentation',
     'OpenStack Foundation', 'manual'),
]
latex_domain_indices = False

latex_elements = {
    'makeindex': '',
    'printindex': '',
    'preamble': r'\setcounter{tocdepth}{3}',
    'maxlistdepth': '10',
}

# Disable usage of xindy https://bugzilla.redhat.com/show_bug.cgi?id=1643664
latex_use_xindy = False

# Disable smartquotes, they don't work in latex
smartquotes_excludes = {'builders': ['latex']}

# -- Options for openstackdocstheme -------------------------------------------

# keep this ordered to keep mriedem happy
openstackdocs_projects = [
    'neutron',
    'nova',
    'oslo.versionedobjects',
    'placement',
    'reno',
]
