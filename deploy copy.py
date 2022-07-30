#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Deploys landscapes defined in the given landscape definition by creating
terraform plan files from templates and calling terraform to maintain them.

Exitcodes:

    0   Everything went fine.
    1   Issues with the command line parameters 
    2   Issues with the planfile

Ideas:
    - 
    - 

ToDo:
    - Adding creation of ansible inventory file
    - If the 'name' shall be used as hostname, we have to honor the restriction:
        "...den ASCII-Zeichen a–z bzw. A–Z (zwischen Groß- und Kleinbuchstaben wird nicht unterschieden), 
         den Ziffern 0–9 und dem Bindestrich-Minus - bestehen. Die einzelnen Labels dürfen nicht mit einem 
         Bindestrich anfangen oder aufhören." 
      Therfore: ^[a-z][a-z0-9-]{1,62}$
    - Schema needs improvement



Changelog:
----------
22.06.2022      v0.1        - and so it beginns..
"""


import os
import re
import schema
import sys
from typing import Tuple
import yaml
import jinja2
import pprint


VERSION = 'v0.1'
AUTHOR = 'soeren.schmidt@suse.com'


def error_and_exit(text: str, exitcode: int = 1) -> None:
    """
    Writes 'text' to stderr and terminates with 'exitcode'.
    """

    print(text, file=sys.stderr)
    sys.exit(exitcode)


def load_landscape(file: str) -> dict:
    """
    Loads the landscape file (YAML) into a dictionary.
    Terminates with error message and exit code 2 on failure.

    The landscape file is first rendered by Jinja2, then interpreted
    as YAML.
    """

    try: 
        with open(file) as f:
            content = yaml.safe_load(jinja2.Template(f.read()).render())
    except Exception as err:
        error_and_exit(f'Error reading landscape: {err}', 2)
    return content
    

def validate(landscape: dict) -> None:
    """
    After schema validation additional checks are done not
    (easy) possible with a schema.

    Terminates with error message and exit code 2 on failure.
    """


    landscape_schema = schema.Schema({
        object: {
            "provider": str,
            "provisioner": str,
            "location": str,
            "subnet": str,
            'name': schema.And(str, 
                               lambda n: True if re.search('^[a-z.][a-z0-9.-]{1,40}$', n) else False,
                               error='"name" must be a string matching "^[a-z.][a-z0-9.-]{1,40}$".'),
            'keymap': str,
            'admin_user': str,
            'admin_user_key': str,
            'subscription_registration_key': str,
            'registration_server': str,
            'enable_root_login': bool,
            "hosts": [
                {   'count': schema.And(int, 
                                        lambda n: True if isinstance(n, int) and n >= 1 else False,
                                        error='"count" must be an integer greater than 1'),
                    schema.Optional('infrastructure'): str,
                    schema.Optional('size'): str,
                    schema.Optional('os'): str
                }
            ]
        }
    }, ignore_extra_keys=False)

    # Validate against schema.
    try:
        landscape_schema.validate(landscape)
    except schema.SchemaError as se:
        msgs = ['Errors during schema validation:'] 
        for err in se.errors + se.autos:
            if err:
                msgs.append(err)
        error_and_exit('\n\t'.join(msgs), 2)

    # Check if providers and provisioners exist.
    hosts_resolved = {}
    for infrastructure in landscape.keys():
        hosts_resolved[infrastructure] = {}

        # Check if providers and provisioners exist.
        for attrib in 'provider', 'provisioner': 
            # TBD...
            print(f'CHECK IF "{attrib}" of "{infrastructure}" EXIST. (NOT YET IMPLEMENTED)')

        # Walk through "hosts".
        for definition in  landscape[infrastructure]['hosts']:
        
            for index in range(1, definition['count']):
                name = f'''{landscape[infrastructure]['name']}{index}'''
                hosts_resolved[infrastructure][name] = definition


    print(hosts_resolved)

def main():

    # We allow one optional argument: the landscape definition.
    if len(sys.argv) > 2:
        error_and_exit(f'Usage: {sys.argv[0]} [LANDSCAPEFILE]\nv{VERSION}')

    # Load and validate landscape.
    landscape_file = sys.argv[1] if len(sys.argv) == 2 else 'landscape.yaml'
    landscape = load_landscape(landscape_file)
    errors = validate(landscape)
    
    #pprint.pprint(landscape)

    # Expand the defaults.
    #host_list, errors = get_hosts(landscape)

    #pprint.pprint(errors)
    #pprint.pprint(host_list)


    # Create a host list for each provider.
    #print([     ])



if __name__ == '__main__':
    main()



 
