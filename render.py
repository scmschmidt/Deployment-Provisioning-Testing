#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pprint
import sys
import yaml
import jinja2


def main():
    try: 
        with open(sys.argv[1]) as f:
            content = jinja2.Template(f.read()).render()
            print(content)
            landscape = yaml.safe_load(content)
    except Exception as err:
        print(f'Error reading landscape: {err}', file=sys.stderr)
        sys.exit(1)



if __name__ == '__main__':
    main()

