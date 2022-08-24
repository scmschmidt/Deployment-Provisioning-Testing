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
    - Implement 'skip' for provisioner (as soon as we have provisioners coded...)
    - Implementation of "excluded_hosts" for provider and provisioner
      For terraform this can get complicated: https://stackoverflow.com/questions/36403998/avoid-to-destroy-the-previously-created-resources
    - Make provider/provisioner outputs more colorful (job of the provider/provisioner!)
    - A "preview_config" command can be useful to show the generated config




Changelog:
----------
22.06.2022      v0.1        - and so it begins...
30.07.2022      v0.2        - Landscape gets validated and checked as far as `deploy`
                              requires it. 
                            - The provider config gets created in the build directory.
01.08.2022      v0.3        - So far we can start the providers.
17.08.2022      v0.4        - Providers work as expected.
18.08.2022      v0.5        - Moving from argparse to docopt, even if the project hasn't seen
                              updates in years. Makes life easier. The function argument_parser()
                              remains, so it can be extended and used again, if docopt gets thrown out.
                            - Implemented showing of provider/provisioner logs.  
"""

import argparse
from cmath import log
import concurrent.futures
import datetime
import docopt
import os
import pathlib
import queue
import re
import readchar
import schema
import shutil
import signal
import subprocess
import sys
import threading
import time
from typing import Tuple, Any
import yaml
import jinja2

# CAN BE REMOVED AFTER DEVELOPMENT.
import pprint



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

def argument_parser() -> object:
    """
    Parses the arguments and return the result object.
    """

#     parser = argparse.ArgumentParser(prog='dpt', 
#                                     usage='%(prog)s [--non-interactive] deploy|destroy LANDSCAPE_FILE\n       %(prog)s showlog_provider PROVIDER\n       %(prog)s -h|--help',
#                                     description='Manages the landscape defined in the landscape file.',
#                                     epilog='')
#     parser.add_argument('command', 
#                         metavar='deploy|destroy',
#                         choices=['deploy', 'destroy'],
#                         help='Command to execute.')
#     parser.add_argument('landscape', 
#                         metavar='LANDSCAPE_FILE',
#                         nargs='?',
#                         default='landscapes/landscape.yaml',
#                         help='Path to the (YAML) landscape definition.')
#     parser.add_argument('--non-interactive', 
#                         dest='interactive',
#                         action='store_false',
#                         help='Do not ask for permission before altering the landscape.')
#     return parser.parse_args()

    description = """
    Usage:
    dpt [--non-interactive] (deploy|destroy) LANDSCAPE_FILE
    dpt [--non-interactive] provide LANDSCAPE_FILE
    dpt (show-provider|show-provisioner) INFRASTRUCTURE
    dpt -h|--help

    Arguments:
    LANDSCAPE_FILE         YAML file describing the landscape. 
    INFRASTRUCTURE         Name of the infrastructure (part of the landscape)  

    Commands:
    deploy ...             Deploys the landscape defined by the landscape file.
    destroy ...            Destroys the landscape defined by the landscape file.
    provide ...            Provides the landscape defined by the landscape file.
    show-provider ...      Shows the provider output (log) of the infrastructure.
    show-provisioner ...   Shows the provisioner output (log) of the infrastructure.

    Options:
    -h --help              Show this help.
    --non-interactive      Do not ask for permission before altering the landscape.
    """

    class MakeObject(object):
        """
        Converting the dict into an object to stay compatible with argparse.
        Also we do some rewrites to stay compatible with older code, that  was
        programmed with argparse instead of docopt.

        - All keys are lowercase.
        - We use 'landscape' instead of 'LANDSCAPE_FILE'.
        - We use 'interactive' instead of '--non-interactive'.
        - 'command' must be set to the selected command.
        """
      
        def __init__(self, arguments):
            
            command = None
            for key in arguments:
                if key == 'LANDSCAPE_FILE':
                    new_key = 'landscape'
                    value = arguments[key]
                elif key == '--non-interactive':
                    new_key = 'interactive'
                    value = not arguments[key]
                elif key in ['deploy', 'destroy', 'provide', 'show-provider', 'show-provisioner'] and arguments[key]:
                    command = key
                    continue
                else:
                    new_key = key
                    value = arguments[key]

                setattr(self, new_key.lower(), value )
            
            if not command:
                CLI.exit_on_error(f'Could not determine the command!', 2)
            else:
                setattr(self, 'command', command)
        
        def __str__(self):
            return str(vars(self))

    # Parse and return the command line arguments.
    return MakeObject(docopt.docopt(description, version=f'{VERSION}'))

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

        build_dir = f'{os.getcwd()}/build/{name}'

        # Generate a few needed provider data.
        try:
            provider_name, provider_args = config['provider'].split()
        except ValueError:
            provider_name = config['provider']
            provider_args = None
        provider_dir = f'''{base_path}/Deployment/providers/{provider_name}'''
        provider_path = f'{provider_dir}/provider'
        if not ( os.path.exists(provider_path) and os.access(provider_path, os.X_OK) ):
            msgs.append(f'''Provider "{config['provider']}": No executable "{provider_path}".''')
            errors = True
            continue 
        
        # Generate a few needed provisioner data.
        try:
            provisioner_name, provisioner_args = config['provisioner'].split()
        except ValueError:
            provisioner_name = config['provisioner']
            provisioner_args = None
        provisioner_dir = f'''{base_path}/Provisioning/provisioners/{provisioner_name}'''
        provisioner_path = f'{provisioner_dir}/provisioner'
        provisioner_config = f'''{build_dir}/config_provisioner'''
        if not ( os.path.exists(provisioner_path) and os.access(provisioner_path, os.X_OK) ):
            msgs.append(f'''Provisioner "{config['provisioner']}": No executable "{provisioner_path}".''')
            errors = True
            continue 

        # Enhance infrastructure with the generated data.
        infrastructures[name] = {}
        infrastructures[name]['config'] = config
        infrastructures[name]['provider_dir'] = provider_dir
        infrastructures[name]['provider_args'] = provider_args
        infrastructures[name]['provisioner_dir'] = provisioner_dir
        infrastructures[name]['provisioner_config'] = provisioner_config
        infrastructures[name]['provider_args'] = provider_args
        infrastructures[name]['build_dir'] = build_dir
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
            with open(f'''{infrastructures[infrastructure]['build_dir']}/config_provider''', 'w') as f: 
                f.write(yaml.safe_dump(infrastructures[infrastructure]))
        except Exception as err:
            CLI.exit_on_error(f'Error setting up build directory for infrastructure "{infrastructure}": {err}', 2)
        CLI.ok(f'''Build directory for infrastructure "{infrastructure}" has bee set up at "{infrastructures[infrastructure]['build_dir']}".''')

def execute(task_definition: Tuple, q) -> None:
    """
    Calls the given executable with the command and the config file as listed
    in the given tuple.
    We wait until the process returns. All output gets captured and we print 
    an info about the running process periodically to show life.
    """

    category, name, provider_dir, command, build_dir = task_definition
    executable = f'{provider_dir}/{category}'

    try:
        start = time.time()
        output_file = open(f'{build_dir}/output_{category}', 'w')
        with subprocess.Popen([executable, command],
                              stdout=output_file, 
                              stderr = subprocess.STDOUT,
                              cwd=build_dir,  
                             ) as proc:
            CLI.print_info(f'[{datetime.datetime.now()}] {category.capitalize()} for "{name}" has been started. (PID: {proc.pid})')
            proc.wait()
        output_file.close()
        end = time.time()
        if proc.returncode == 0:
            CLI.ok(f'{category.capitalize()} for "{name}" has terminated successfully. (Executed in {round(end-start, 1)}s)')
        else:
            CLI.fail(f'{category.capitalize()} for "{name}" failed with exit code {proc.returncode}! (Executed in {round(end-start, 1)}s)\n\t-> Run "./dpt show-{category} {name}" for details')
            q.put(True)
    except Exception as err:
        CLI.fail(f'Could not execute {category} for landscape "{name}": {err}')
        q.put(True)

def fire_threads(call_list: list) -> bool:
    """
    Start all threads in the call list in parallel and waiting for termination.
    The progress will be shown by a spinner.

    Returns True if *all* threads terminated successfully else False.
    """
    try:              
        q = queue.Queue()
        jobs = [threading.Thread(target=execute, args=(params, q)) for params in call_list]
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
        thread_errors  = [q.get() for _ in range(q.qsize())]       
        if True in thread_errors:
            return False
    except Exception as err:
        CLI.exit_on_error(f'[{datetime.datetime.now()}] Fatal error during execution: {err}', 3)
    return True

def show_log(path: str) -> None:
    """
    Reads the file and prints it to stdout.
    """

    try:
        with open(path, 'r') as f:
            for line in f.readlines():
                print(line.strip())
    except Exception as err:
        CLI.exit_on_error(f'Error reading log for infrastructure: {err}', 3)


def main():

    # Terminate nicely at ^C.
    signal.signal(signal.SIGINT, signal_handler)

    # Parsing arguments.
    args = argument_parser()

    # Extract DTP base path from the link of this script.
    base_path = os.path.dirname(pathlib.Path(sys.argv[0]).resolve())

    # We shall show the results of a provider run.
    if args.command == 'show-provider':

        # Print log and terminate.
        show_log(f'./build/{args.infrastructure}/output_provider')
        sys.exit(0) 

    # We shall show the results of a provisioner run.
    if args.command == 'show-provisioner':

        # Print log and terminate.
        show_log(f'./build/{args.infrastructure}/output_provisioner')
        sys.exit(0) 

    # Load and validate landscape.
    landscape = load_landscape(args.landscape)
    infrastructures = validate(landscape, base_path)

    # Now only commands follow, which have a destructive nature,
    # so we ask for permission.
    if args.interactive and not wait_for_key("Shall we deploy? [Y|n]", { 'Y': True, 'n': False}):
        CLI.exit_on_error('User interruption. Terminating.', 2)
    
    # We shall do something with the provider.
    if args.command in ['deploy', 'destroy']:

        # Create working data for the providers.
        setup_infrastructures(infrastructures)

        CLI.header('Execute providers')

        # Calling the providers of each infrastructure.
        if not fire_threads([('provider', name, data['provider_dir'], args.command, data['build_dir']) for name, data in infrastructures.items()]):
            CLI.exit_on_error(f'[{datetime.datetime.now()}] Deployment failed', 3)

        # Bye.
        CLI.print_info(f'[{datetime.datetime.now()}] Deployment finished')
        sys.exit(0)
    
    # We shall do something with the provisioner.
    if args.command == 'provide':

        CLI.header('Execute provisioners')

        # Calling the provisioners of each infrastructure.
        if not fire_threads([('provisioner', name, data['provisioner_dir'], args.command, data['build_dir']) for name, data in infrastructures.items()]):
            CLI.exit_on_error(f'[{datetime.datetime.now()}] Provisioning failed.', 3)

        # Bye.
        CLI.print_info(f'[{datetime.datetime.now()}] Provisioning finished')
        sys.exit(0)

    # Bye.
    CLI.exit_on_error(f'No action done. Command "{args.command}" seems to be unknown...', 2)


if __name__ == '__main__':
    main()



 
