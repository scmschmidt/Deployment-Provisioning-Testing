#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Usage:
dpt [--non-interactive] (deploy|destroy) LANDSCAPE_FILE
dpt show (provider|provisioner) INFRASTRUCTURE
dpt -h|--help

Commands:
deploy LANDSCAPE_FILE             Deploys the landscape defined by the landscape file.
destroy LANDSCAPE_FILE            Destroys the landscape defined by the landscape file.
show provider INFRASTRUCTURE      Shows the provider output (log) of the infrastructure.
show provisioner INFRASTRUCTURE   Shows the provisioner output (log) of the infrastructure.

Options:
-h --help          Show this help.
--non-interactive  Do not ask for permission before altering the landscape.
"""
from docopt import docopt


if __name__ == '__main__':
    arguments = docopt(__doc__, version='Naval Fate 2.0')
    print(arguments)