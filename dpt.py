#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Deploys landscapes defined in the given landscape definition by calling the
configured providers and handing over the relevant configuration.

Exitcodes:

    0   Everything went fine.
    1   Issues with the command line parameters 
    2   Issues with the planfile

Ideas:
    - 
    - 

ToDo:
    - Schema needs improvement



Changelog:
----------
22.06.2022      v0.1        - and so it begins...
30.07.2022      v0.2        - Landscape gets validated and checked as far as `deploy`
                              requires it. 
                            - The provider config gets created in the build directory.

"""

import argparse
import concurrent.futures
import os
import pathlib
import re
import readchar
import schema
import shutil
import subprocess
import sys
from typing import Tuple, Any
import yaml
import jinja2

import pprint
import time


VERSION = 'v0.2'
AUTHOR = 'soeren.schmidt@suse.com'

class CLI:
    """
    Class to print colorful text on the command line interface.
    """

    PURPLE = '\033[95m'
    CYAN = '\033[96m'
    DARKCYAN = '\033[36m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    _END = '\033[0m'

    @classmethod
    def print(cls, text: str = '', **kwargs) -> None:
        print(text, **kwargs)

    @classmethod
    def print_info(cls, text: str = '', end: str = '\n') -> None:
        print(f'{cls.BLUE}{cls.BOLD}{text}{cls._END}', end=end)

    @classmethod
    def print_important(cls, text: str = '', end: str = '\n') -> None:
        print(f'{cls.PURPLE}{cls.BOLD}{text}{cls._END}', end=end)

    @classmethod
    def print_fmt(cls, text: str = '', fmt: str = '', end: str = '\n') -> None:
        print(f'''{fmt}{text}{cls._END if fmt else ''}''', end=end, flush=True)

    @classmethod
    def header(cls, text: str = '') -> None:
        print(f'\n{cls.BOLD}{cls.UNDERLINE}{text}{cls._END}')

    @classmethod
    def ok(cls, text: str = '') -> None:
        print(f'[{cls.GREEN} OK {cls._END}] {text}')

    @classmethod
    def note(cls, text: str = '') -> None:
        print(f'[{cls.BLUE}NOTE{cls._END}] {cls.BOLD}{text}{cls._END}')

    @classmethod
    def warn(cls, text: str = '') -> None:
        print(f'[{cls.YELLOW}WARN{cls._END}] {text}')

    @classmethod
    def fail(cls, text: str = '') -> None:
        print(f'[{cls.RED}FAIL{cls._END}] {cls.BOLD}{text}{cls._END}')

    @classmethod
    def exit_on_error(cls, text: str, exitcode: int = 1):
        print(f'{cls.RED}{text}{cls._END}', file=sys.stderr)
        sys.exit(exitcode)


def wait_for_key(text: str, mapping: dict) -> Any:
    """
    Prints the text and waits for the keys defined in the mapping
    and returns the associate string after the key has been pressed.
    """

    CLI.print_important(f'\n{text}')
    while True:
        k = readchar.readkey()
        if k in mapping.keys():
            return mapping[k]

def load_config(config: str) -> dict:
    """
    Loads the config.
    """
    CLI.header('Load configuration ((DO WE NEED THIS???????)')
    try: 
        with open(config) as f:
            content = yaml.safe_load(f.read())
    except Exception as err:
        CLI.exit_on_error(f'Error reading config: {err}', 2)
    CLI.ok(f'Configuration "{config} loaded successfully.')
    return content

def load_landscape(file: str) -> dict:
    """
    Loads the landscape file (YAML) into a dictionary.
    Terminates with error message and exit code 2 on failure.

    The landscape file is first rendered by Jinja2, then interpreted
    as YAML.
    """

    CLI.header('Load landscape')
    try: 
        with open(file) as f:
            content = yaml.safe_load(jinja2.Template(f.read()).render())
    except Exception as err:
        CLI.exit_on_error(f'Error reading landscape: {err}', 2)

    # Check for an empty landscape.
    if not content:
        CLI.exit_on_error(f'The landscape "{file}" is empty!', 2)

    CLI.ok(f'Landscape "{file} loaded successfully.')
    return content
    
def validate(landscape: dict, base_path: str) -> dict:
    """
    After schema validation additional checks are done not
    (easy) possible with a schema.
    The schema here only validates the parts needed to call 
    the provider. It is in the responsibility of the provider
    to do additional verifications.
    Also it builds up a deployment dictionary with the details
    about each infrastructure and their providers (paths and configs).

    Terminates with error message and exit code 2 on failure.
    """

    CLI.header('Validate landscape')

    landscape_schema = schema.Schema({
        object: {
            "provider": str,
            "hosts": list,
        }
    }, ignore_extra_keys=True)

    # Validate against schema.
    try:
        landscape_schema.validate(landscape)
    except schema.SchemaError as se:
        msgs = ['Errors during schema validation:'] 
        for err in se.errors + se.autos:
            if err:
                msgs.append(err)
        CLI.exit_on_error('\n\t'.join(msgs), 2)
    CLI.ok('Schema validation passed.')

    # Create deployment data.
    infrastructures = {}
    msgs = ['Error during provider validation:']
    errors = False
    for name, config in landscape.items():
        provider_path = f'''{base_path}/Deployment/providers/{config['provider']}/provider'''
        if not ( os.path.exists(provider_path) and os.access(provider_path, os.X_OK) ):
            msgs.append(f'''Provider "{config['provider']}": No executable "{provider_path}".''')
            errors = True
            continue 
        infrastructures[name] = {}
        infrastructures[name]['config'] = config
        infrastructures[name]['provider_path'] = provider_path
        infrastructures[name]['build_path'] = f'build/{name}'
        infrastructures[name]['config_path'] = f'build/{name}/config'
        CLI.ok(f'Infrastructure "{name}" configured.')
    if errors: 
        CLI.exit_on_error('\n\t'.join(msgs), 2)
    CLI.ok('All providers exist.')

    return infrastructures

def setup_infrastructures(infrastructures: dir) -> None:
    """
    Creates the necessary files for the infrastructures.

    Terminates with error message and exit code 2 on failure.
    """
    CLI.header('Set up infrastructures')
    for infrastructure in infrastructures:
        try:
            if os.path.exists(infrastructures[infrastructure]['build_path']):
                shutil.rmtree(infrastructures[infrastructure]['build_path'])
            os.mkdir(infrastructures[infrastructure]['build_path'], mode = 0o700)
            with open(infrastructures[infrastructure]['config_path'], 'w') as f: 
                f.write(yaml.safe_dump(infrastructures[infrastructure]['config']))
        except Exception as err:
            CLI.exit_on_error(f'Error setting up build directory for infrastructure "{infrastructure}": {err}', 2)
        CLI.ok(f'''Build directory for infrastructure "{infrastructure}" has bee set up at "{infrastructures[infrastructure]['build_path']}".''')

def execute_provider(provider_def: Tuple) -> None:
    """
    Calls the given executable with the command and the config file as listed
    in the given tuple.
    We wait until the process returns. All output gets captured we print 
    an info about the running process periodically to show life.
    """
    
    name, executable, command, config_file = provider_def

    # Starting the provider and wait for its return.
    with subprocess.Popen([executable, command, config_file], 
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE
                         ) as proc:
        CLI.print_info(f'Provider for "{name}" has been started. (PID: {proc.pid})')
        c = 0
        while proc.poll() == None:
            c += 1
            if c % 10 == 0:
                CLI.print_info(f'Provider for "{name}" still running...')
            time.sleep(.1)
    
    # Print results.
    if proc.returncode == 0:
        CLI.ok(f'Provider for "{name}" has terminated successfully.')
        #print(proc.stdout.read())
    else:
        CLI.fail(f'Provider for "{name}" failed!\nreturncode: {proc.returncode}\nstderr:\n{proc.stderr.read()}')
        #CLI.print_important(proc.stderr.read())
    # Printing result
    raise !!!!!!!


def main():

    # Parsing arguments.
    parser = argparse.ArgumentParser(prog='dpt', 
                                    usage='%(prog)s [--non-interactive] apply|destroy LANDSCAPE_FILE',
                                    description='Manages the landscape defined in the landscape file.',
                                    epilog='')
    parser.add_argument('command', 
                        metavar='apply|destroy',
                        choices=['apply', 'destroy'],
                        help='Command to execute.')
    parser.add_argument('landscape', 
                        metavar='LANDSCAPE_FILE',
                        nargs='?',
                        default='landscapes/landscape.yaml',
                        help='Path to the (YAML) landscape definition.')
    parser.add_argument('--non-interactive', 
                        dest='interactive',
                        action='store_false',
                        help='Do not ask for permission before altering the landscape.')
    args = parser.parse_args()

    # First we load the config.   DO WE REALLY NEED THIS??????????????????????????
    config = load_config('.DTP/config')

    # Extract DTP base path from the link of this script.
    base_path = os.path.dirname(pathlib.Path(sys.argv[0]).resolve())

    # Load and validate landscape.
    landscape = load_landscape(args.landscape)
    infrastructures = validate(landscape, base_path)

    # Create working data for the providers.
    setup_infrastructures(infrastructures)

    # If in interactive mode, we aks before we call to action.
    if args.interactive:
        doit = wait_for_key("Shall we deploy? [Y|n]", { 'Y': True, 'n': False}) 
    else:
        doit = True

    if doit:
        CLI.header('Execute providers')

        # Calling the providers of each infrastructure.
        call_list = [(name, data['provider_path'], args.command, data['config_path']) for name, data in infrastructures.items()]
        try:
            with concurrent.futures.ThreadPoolExecutor() as executor:
                executor.map(execute_provider, call_list)    
        except Exception as err:
            CLI.exit_on_error(f'Fatal error during provider execution: {err}', 3)

        # Running provider in parallel.


        # Collecting results.

        # Writing final report.
        CLI.print_info("Deployment finished")

    else:
        CLI.exit_on_error('User interruption. Terminating.', 2)

    print('WE NEED A SIGNAL HANDLER')

    # Bye.
    sys.exit(0)

if __name__ == '__main__':
    main()



 
