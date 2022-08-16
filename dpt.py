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
    - We need to capture ^C   (atexit???)
    - Provider requires implementation of "excluded_hosts" (terraform's lifecycle feature)
    - Add commands for viewing the provider/provisioner outputs.



Changelog:
----------
22.06.2022      v0.1        - and so it begins...
30.07.2022      v0.2        - Landscape gets validated and checked as far as `deploy`
                              requires it. 
                            - The provider config gets created in the build directory.
01.08.2022      v0.3        - So far we can start the providers.
"""

import argparse
import concurrent.futures
import datetime
import os
import pathlib
import re
import readchar
import schema
import shutil
import signal
import subprocess
import sys
import threading
from typing import Tuple, Any
import yaml
import jinja2

# CAN BE REMOVED AFTER DEVELOPMENT.
import pprint
import time


VERSION = 'v0.3'
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



def signal_handler(signal, frame):
    """ 
    Terminate with exit code 1.
    """
    print(threading.active_count() )
    time.sleep(3)
    #sys.exit(1)

def argument_parser() -> object:
    """
    Parses the arguments and return the argparse object.
    """

    parser = argparse.ArgumentParser(prog='dpt', 
                                    usage='%(prog)s [--non-interactive] deploy|destroy LANDSCAPE_FILE',
                                    description='Manages the landscape defined in the landscape file.',
                                    epilog='')
    parser.add_argument('command', 
                        metavar='deploy|destroy',
                        choices=['deploy', 'destroy'],
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
    return parser.parse_args()

def spinner_generator() -> str:
    """
    Returns on each call the next char for a spinner.
    """
    spinner = '-\|/'
    while True:
        for char in spinner:
            yield str(char)

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

# DO WE NEED THIS???????)
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
    Loads the given landscape file (YAML).
    Terminates with error message and exit code 2 on failure.

    The landscape file is first rendered by Jinja2, then interpreted
    as YAML. THe directory where the file is in, will be used as a 
    template directory for Jinja2. Therefore extending and including 
    is possible.
    """

    CLI.header('Load landscape')
    try: 
        dirname, filename = os.path.split(file)
        env = jinja2.Environment(loader=jinja2.FileSystemLoader(dirname))
        template = env.get_template(filename)
        content = yaml.safe_load(template.render())
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
            'provider': str,
            'hosts': list,
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
        provider_name, provider_args = config['provider'].split()
        provider_dir = f'''{base_path}/Deployment/providers/{provider_name}'''
        provider_path = f'{provider_dir}/provider'
        if not ( os.path.exists(provider_path) and os.access(provider_path, os.X_OK) ):
            msgs.append(f'''Provider "{config['provider']}": No executable "{provider_path}".''')
            errors = True
            continue 
        infrastructures[name] = {}
        infrastructures[name]['config'] = config
        infrastructures[name]['provider_dir'] = provider_dir
        infrastructures[name]['provider_args'] = provider_args
        infrastructures[name]['build_dir'] = f'{os.getcwd()}/build/{name}'
        infrastructures[name]['config']['name'] = name
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
            if not os.path.exists(infrastructures[infrastructure]['build_dir']):
                os.mkdir(infrastructures[infrastructure]['build_dir'], mode = 0o700)
            with open(f'''{infrastructures[infrastructure]['build_dir']}/config''', 'w') as f: 
                f.write(yaml.safe_dump(infrastructures[infrastructure]))
        except Exception as err:
            CLI.exit_on_error(f'Error setting up build directory for infrastructure "{infrastructure}": {err}', 2)
        CLI.ok(f'''Build directory for infrastructure "{infrastructure}" has bee set up at "{infrastructures[infrastructure]['build_dir']}".''')

def execute_provider(provider_def: Tuple) -> None:
    """
    Calls the given executable with the command and the config file as listed
    in the given tuple.
    We wait until the process returns. All output gets captured and we print 
    an info about the running process periodically to show life.
    """

    name, provider_dir, command, build_dir = provider_def
    executable = f'{provider_dir}/provider'

    try:
        start = time.time()
        output_file = open(f'{build_dir}/output', 'w')
        with subprocess.Popen([executable, command],
                              stdout=output_file, 
                              stderr = subprocess.STDOUT,
                              cwd=build_dir,  
                             ) as proc:
            CLI.print_info(f'[{datetime.datetime.now()}] Provider for "{name}" has been started. (PID: {proc.pid})')
            proc.wait()
        output_file.close()
        end = time.time()
        if proc.returncode == 0:
            CLI.ok(f'Provider for "{name}" has terminated successfully. (Executed in {round(end-start, 1)}s)')
        else:
            CLI.fail(f'Provider for "{name}" failed with exit code {proc.returncode}! (Executed in {round(end-start, 1)}s)\n\t-> See "{output_file.name}" for details')
    except Exception as err:
        CLI.fail(err)


def main():

    # Terminate nicely at ^C.
    signal.signal(signal.SIGINT, signal_handler)

    # Parsing arguments.
    args = argument_parser()

    # First we load the config.   DO WE REALLY NEED THIS??????????????????????????
    config = load_config('.DTP/config')

    # Extract DTP base path from the link of this script.
    base_path = os.path.dirname(pathlib.Path(sys.argv[0]).resolve())

    # Load and validate landscape.
    landscape = load_landscape(args.landscape)
    infrastructures = validate(landscape, base_path)

    # Command switch.
    #sys.exit(0)

    # These are commands intended for the provider.
    if args.command in ['deploy', 'destroy']:

        # Create working data for the providers.
        setup_infrastructures(infrastructures)

        # If in interactive mode, we aks before we call to action.
        if args.interactive:
            doit = wait_for_key("Shall we deploy? [Y|n]", { 'Y': True, 'n': False}) 
        else:
            doit = True

        if doit:
            CLI.header('Execute providers')

            CLI.warn('WE NEED A SIGNAL HANDLER')

            # Calling the providers of each infrastructure.
            call_list = [(name, data['provider_dir'], args.command, data['build_dir']) for name, data in infrastructures.items()]
            try:
                jobs = [threading.Thread(target=execute_provider, args=(params,)) for params in call_list]
                for job in jobs:
                    job.start()
                spinner = spinner_generator()
                start = time.time()
                while len(jobs) > 0:
                    for job in jobs:
                        CLI.print_fmt(f'Running: {len(jobs)}/{len(call_list)} ({round(time.time()-start,1)}s) {next(spinner)}', fmt=CLI.BOLD+CLI.CYAN, end='\r')
                        if not job.is_alive():
                            jobs.remove(job)
                        time.sleep(.1)

            except Exception as err:
                CLI.exit_on_error(f'[{datetime.datetime.now()}] Fatal error during provider execution: {err}', 3)

            CLI.print_info(f'[{datetime.datetime.now()}] Deployment finished')

        else:
            CLI.exit_on_error('User interruption. Terminating.', 2)

        # Translate commands into terraform commands
        #terraform_command = {'deploy': 'apply', 'destroy'}[sys.argv[1]]

        # WE HAVE TO DEAL WITH ERRORS FROM THE PROVIDER
        # NOW WE HAVE TO TAKE THE PROVIDER RESULT AND PLACE IT FOR THE PROVISIONER

    # This is the command to show the results of provider an provisioner runs.
    if args.command == 'show':
        pass



    # Bye.
    sys.exit(0)

if __name__ == '__main__':
    main()



 
