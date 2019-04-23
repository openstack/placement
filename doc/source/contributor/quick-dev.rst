..
      Licensed under the Apache License, Version 2.0 (the "License"); you may
      not use this file except in compliance with the License. You may obtain
      a copy of the License at

          http://www.apache.org/licenses/LICENSE-2.0

      Unless required by applicable law or agreed to in writing, software
      distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
      WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
      License for the specific language governing permissions and limitations
      under the License.

===========================
Quick Placement Development
===========================

.. note:: This is one of many ways to achieve a simple *live* development
          environment for the placement service. This isn't meant to be the
          best way, or the only way. Its purpose is more to demonstrate the
          steps involved, so that people can learn from those steps and choose
          to assemble them in whatever ways work best for them.

          This content was originally written in a `blog post
          <https://anticdent.org/quick-placement-development.html>`_, which
          perhaps explains its folksy tone.

Here are some instructions on how to spin up the placement wsgi script with
uwsgi and a stubbed out ``placement.conf``, in case you want to see what
happens.  The idea here is that you want to experiment with the current
placement code, using a live database, but you're not concerned with other
services, don't want to deal with devstack, but need a level of interaction
with the code and process that something like `placedock
<https://github.com/cdent/placedock>`_ can't provide.

*As ever, even all of the above has lots of assumptions about experience and
context. This document assumes you are someone who either is an OpenStack (and
probably placement) developer, or would like to be one.*

To make this go you need a unix-like OS, with a python3 dev environment, and
git and mysql (or postgresql) installed. We'll be doing this work from within a
virtualenv, built from the ``tox.ini`` in the placement code.

Get The Code
============

The placement code lives at
https://opendev.org/openstack/placement . We want to clone that::

    git clone https://opendev.org/openstack/placement
    cd placement

Setup The Database
==================

We need to 1) create the database, 2) create a virtualenv to have the command,
3) use it to create the tables.

The database can have whatever name you like. Whatever you choose, use it
throughout this process. We choose ``placement``. You may need a user and
password to talk to your database, setting that up is out of scope for this
document::

    mysql -uroot -psecret -e "DROP DATABASE IF EXISTS placement;"
    mysql -uroot -psecret -e "CREATE DATABASE placement CHARACTER SET utf8;"

You may also need to set permissions::

    mysql -uroot -psecret \
        -e "GRANT ALL PRIVILEGES ON placement.* TO 'root'@'%' identified by 'secret';"

Create a bare minimum placement.conf in the ``/etc/placement``
directory (which you may need to create)::

    [placement_database]
    connection = mysql+pymysql://root:secret@127.0.0.1/placement?charset=utf8

.. note:: You may choose the location of the configuration file on the command
          line when using the ``placement-manage`` command.

Make the ``placement-manage`` command available by updating a virtualenv::

    tox -epy36 --notest

Run the command to create the tables::

    .tox/py36/bin/placement-manage db sync

You can confirm the tables are there with ``mysqlshow placement``

Run The Service
===============

Now we want to run the service. We need to update ``placement.conf`` so it will
produce debugging output and use the ``noauth`` strategy for authentication (so
we don't also have to run Keystone). Make ``placement.conf`` look like this
(adjusting for your database settings)::

    [DEFAULT]
    debug = True

    [placement_database]
    connection = mysql+pymysql://root:secret@127.0.0.1/placement?charset=utf8

    [api]
    auth_strategy = noauth2

We need to install the uwsgi package into the virtualenv::

    .tox/py36/bin/pip install uwsgi

And then use uwsgi to run the service. Start it with::

    .tox/py36/bin/uwsgi --http :8000 --wsgi-file .tox/py36/bin/placement-api --processes 2 --threads 10

.. note:: Adjust ``processes`` and ``threads`` as required. If you do not
          provide these arguments the server will be a single process and
          thus perform poorly.

If that worked you'll see lots of debug output and ``spawned uWSGI worker``.
Test that things are working from another terminal with curl::

    curl -v http://localhost:8000/

Get a list of resource providers with (the ``x-auth-token`` header is
required, ``openstack-api-version`` is optional but makes sure we are getting
the latest functionality)::

    curl -H 'x-auth-token: admin' \
         -H 'openstack-api-version: placement latest' \
         http://localhost:8000/resource_providers

The result ought to look something like this::

    {"resource_providers": []}

If it doesn't then something went wrong with the above and there should be more
information in the terminal where ``uwsgi`` is running.

From here you can experiment with creating resource providers and related
placement features. If you change the placement code, ``ctrl-c`` to kill the
uwsgi process and start it up again. For testing, you might enjoy
`placecat <https://github.com/cdent/placecat>`_.

Here's all of the above as single script. As stated above this is for
illustrative purposes. You should make your own::

    #!/bin/bash

    set -xe

    # Change these as required
    CONF_DIR=/etc/placement
    DB_DRIVER=mysql+pymysql # we assume mysql throughout, feel free to change
    DB_NAME=placement
    DB_USER=root
    DB_PASS=secret

    REPO=https://opendev.org/openstack/placement

    # Create a directory for configuration to live.
    [[ -d $CONF_DIR ]] || (sudo mkdir $CONF_DIR && sudo chown $USER $CONF_DIR)

    # Establish database. Some of this may need sudo powers. Don't be shy
    # about changing the script.
    mysql -u$DB_USER -p$DB_PASS -e "DROP DATABASE IF EXISTS $DB_NAME;"
    mysql -u$DB_USER -p$DB_PASS -e "CREATE DATABASE $DB_NAME CHARACTER SET utf8;"
    mysql -u$DB_USER -p$DB_PASS -e "GRANT ALL PRIVILEGES ON $DB_NAME.* TO '$DB_USER'@'%' IDENTIFIED BY '$DB_PASS';"

    # clone the right code
    git clone $REPO
    cd placement

    # establish virtenv
    tox -epy36 --notest

    # write placement.conf
    cat<<EOF > $CONF_DIR/placement.conf
    [DEFAULT]
    debug = True

    [placement_database]
    connection = $DB_DRIVER://${DB_USER}:${DB_PASS}@127.0.0.1/${DB_NAME}?charset=utf8

    [api]
    auth_strategy = noauth2
    EOF

    # Create database tables
    .tox/py36/bin/placement-manage db sync

    # install uwsgi
    .tox/py36/bin/pip install uwsgi

    # run uwsgi
    .tox/py36/bin/uwsgi --http :8000 --wsgi-file .tox/py36/bin/placement-api --processes 2 --threads 10
