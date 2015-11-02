#!/usr/bin/env python3
#
# Ubuntu System Tests
# Copyright (C) 2014, 2015 Canonical
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from upgrade_testing.provisioning import backends
from upgrade_testing.configspec import definition_reader, test_source_retriever

import datetime
import logging
import os
import subprocess
import tempfile
import yaml

from argparse import ArgumentParser
from textwrap import dedent

logger = logging.getLogger(__name__)


def parse_args():
    """
    do_setup (better name) if the backend isn't setup do it.
    """
    parser = ArgumentParser('Run system tests for Upgrade Tests.')
    parser.add_argument(
        '--config', '-c',
        help='The config file to use for this run.')
    parser.add_argument(
        '--provision',
        default=False,
        action='store_true',
        help='Provision the requested backend')
    parser.add_argument(
        '--results-dir',
        help='Directory to store results generated during the run.')
    return parser.parse_args()


def prepare_environment(testsuite, temp_file):
    """Write testrun config details to `temp_file`.

    :param testsuite: TestSpecification instance.

    """
    pre_tests = ' '.join(testsuite.pre_upgrade_scripts)
    post_tests = ' '.join(testsuite.post_upgrade_tests)
    temp_file.write(
        dedent('''\
        # Auto Upgrade Test Configuration
        export PRE_TEST_LOCATION="/root/pre_scripts"
        export POST_TEST_LOCATION="/root/post_scripts"
        '''))
    temp_file.write('PRE_TESTS_TO_RUN="{}"\n'.format(pre_tests))
    temp_file.write('POST_TESTS_TO_RUN="{}"\n'.format(post_tests))


def get_output_dir(args):
    """Return directory path that the results should be put into.

    If no directory is provided in the commandline args then create a temp
    dir. It is the responsibility of the script runner to clean up this temp
    dir.

    Within this base dir a timestamped directory will be created in which the
    output will reside.

    """
    if args.results_dir is not None:
        base_dir = args.results_dir
    else:
        base_dir = tempfile.mkdtemp(prefix='upgrade-tests')
        logger.info('Creating folder for results.')

    ts_dir = datetime.datetime.now().strftime('%Y%m%d.%H%M%S')
    full_path = os.path.join(os.path.abspath(base_dir), ts_dir)

    logger.info('Creating results dir: ', full_path)
    os.makedirs(full_path, exist_ok=True)

    return full_path


def display_results(artifacts_directory):
    # Read in yaml results file and output results.
    results_yaml = os.path.join(artifacts_directory, 'runner_results.yaml')
    with open(results_yaml, 'r') as f:
        results = yaml.safe_load(f)

    # this can be html/xml/whatver
    output = []
    output.append('Pre script results:')
    for test, result in results['pre_script_output'].items():
        output.append('\t{test}: {result}'.format(test=test, result=result))

    output.append('Post upgrade test results:')
    for test, result in results['post_test_output'].items():
        output.append('\t{test}: {result}'.format(test=test, result=result))
    print('\n'.join(output))


def execute_adt_run(testsuite, backend, run_config_file, output_dir):
    """Prepare the adt-run to execute.

    Copy all the files into the expected place etc.

    :param testsuite: Dict containing testsuite details
    :param backend:  provisioning backend object
    :param test_file_name: filepath for . . .
    """
    with test_source_retriever(testsuite.test_source) as test_source_dir:
        adt_run_command = get_adt_run_command(
            backend,
            run_config_file,
            test_source_dir,
            output_dir,
        )
        subprocess.check_call(adt_run_command)


def get_adt_run_command(backend, run_config, test_source_dir, results_dir):
    """Construct the adt command to run.

    :param testsuite: TestSpecification object containing test run details.

    """
    # Default adt-run hardcoded adt command
    adt_cmd = [
        'adt-run',
        '-B',
        '--user=root',
        '--unbuilt-tree=.',
        '--output-dir={}'.format(results_dir),
    ]

    # Copy across the test scripts.
    dest_dir = '/root/run_scripts/'
    copy_cmd = '--copy={src}:{dest}'.format(
        src=test_source_dir,
        dest=dest_dir
    )
    adt_cmd.append(copy_cmd)

    # Need to get some env vars across to the testbed. Namely tests to run and
    # test locations.
    adt_cmd.append(
        '--copy={}:/root/auto_upgrade_test_settings'.format(run_config))

    backend_args = backend.get_adt_run_args()

    return adt_cmd + ['---'] + backend_args


def main():
    args = parse_args()

    # if args.provision_file etc. . .
    test_def_details = definition_reader(args.config)

    # For each test definition ensure that the required backend is available,
    # if not either error or create it (depending on args.)
    for testsuite in test_def_details:
        backend = backends.get_backend(testsuite.provisioning)

        if not backend.available():
            if args.provision:
                logger.info('Creating backend for: {}'.format(backend))
                backend.create()
            else:
                logger.error('No available backend for test: {}'.format(
                    testsuite.name)
                )
                continue
        else:
            logger.info('Backend "{}" is available.'.format(backend))

        # Setup output dir
        output_dir = get_output_dir(args)

        try:
            temp_file_name = tempfile.mkstemp()[1]
            with open(temp_file_name, 'w') as temp_file:
                prepare_environment(testsuite, temp_file)

            execute_adt_run(testsuite, backend, temp_file_name, output_dir)
        finally:
            os.unlink(temp_file_name)

        artifacts_directory = os.path.join(
            output_dir, 'artifacts', 'upgrade_run'
        )
        logger.info(
            'Results can be found here: {}'.format(artifacts_directory)
        )
        display_results(artifacts_directory)


if __name__ == '__main__':
    main()
