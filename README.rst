===============
AWS Cost Report
===============

Simple example script to generate a TSV file using the `AWS Cost Explorer API <https://aws.amazon.com/blogs/aws/new-interactive-aws-cost-explorer-api/>`_.

Usage:

.. code-block:: bash

    $ # login to consolidated billing account
    $ pip3 install -U boto3
    $ ./aws-cost-and-usage-report.py --days=7 >> results.tsv

The ``results.tsv`` file can be opened in your favorite spreadsheet application. Its contents look like:

========== ============= ====================================== ====== ==== =========
TimeSpan   LinkedAccount InstanceType 				Amount Unit Estimated
========== ============= ====================================== ====== ==== =========
2019-07-07 123123123123  EC2		                        12.34  USD  False
.
.
========== ============= ====================================== ====== ==== =========
