# -*- coding:utf-8 -*-
"""
Implementation of the sitcpy command executed in global scope.
In order to use the sitcpy command, pip installation is required.

Copyright (c) 2018, Bee Beans Technologies Co.,Ltd.
"""

import argparse
import os
import shutil
import sys

import sitcpy


EXIT_SUCCESS = 0
EXIT_FAILURE = 1


def command_createcuiproject(args):
    print("Create cui project.")
    print("project-name = %s" % args.name)
    print("abs-path = %s" % os.path.abspath(args.name))

    if not args.name:
        print("\nERROR: Argument 'name' is empty.")
        sys.exit(EXIT_FAILURE)

    if os.path.exists(args.name):
        print("\nERROR: File or directory is already exitsts.")
        sys.exit(EXIT_FAILURE)

    template_path = (
        os.path.join(os.path.dirname(os.path.abspath(sitcpy.__file__)),
                     "templates",
                     "cui_project"))
    print("template-dir = %s" % template_path)
    print("")

    os.mkdir(args.name)

    with open(os.path.join(template_path, "templates.txt")) as f:
        for path in [line.strip() for line in f.readlines()]:
            if not path or path.startswith("#"):
                continue

            dirs = os.path.join(args.name, os.path.dirname(path))
            if not os.path.exists(dirs):
                os.makedirs(dirs)

            src = os.path.join(template_path, path)
            dst = os.path.abspath(os.path.join(args.name, path))
            print("Copy file from '%s' to '%s'" % (src, dst))
            shutil.copyfile(src, dst)

    print("\nThe project was initialized successfully.")


def main(args=None):

    # Root parser
    parser = argparse.ArgumentParser(
        description="sitcpy command. See sub-command help.")

    # Sub parsers
    subparsers = parser.add_subparsers()

    # parser of createcuiproject sub-command.
    createcuiproject = subparsers.add_parser(
        "createcuiproject",
        description=(
            "Create a python cui project to communicate with the "
            "SiTCP device. The project includes a simple simulator "
            "of the SiTCP device."),
        help=("Create a python cui project to communicate with the SiTCP "
              "device. See `createcuiproject -h`"))

    createcuiproject.add_argument(
        "name", type=str,
        help=("A subdirectory is created with this name and the project is "
              "initialized."))

    createcuiproject.set_defaults(handler=command_createcuiproject)

    # Parse args
    args = parser.parse_args(args)
    if hasattr(args, "handler"):
        args.handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
    sys.exit(EXIT_SUCCESS)
