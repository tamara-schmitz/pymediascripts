#!/usr/bin/python3

# Requires cjxl and optionally magick command!

import os
import shutil
from pathlib import Path
import tempfile
import unicodedata
import textwrap
import argparse
import sys
import subprocess
import random
import string
import re
from concurrent import futures

def exec_cmd(cmd, output=None):
    if isinstance(cmd, str):
        cmd = cmd.split(' ')

    if sys.platform == 'win32':
        # TODO priority does not appear to be set properly
        si = subprocess.STARTUPINFO()
        si.dwFlags = subprocess.BELOW_NORMAL_PRIORITY_CLASS
        if args.v:
            print("  Executing command: {}".format(cmd))
        return subprocess.run(cmd, shell=False, stdout=output, stderr=subprocess.STDOUT, startupinfo=si)
    elif sys.platform == 'linux' or sys.platform == 'darwin':
        cmd.insert(0, "nice")
        cmd.insert(1, "-n19")
        if args.v:
            print("  Executing command: {}".format(cmd))
        return subprocess.run(cmd, shell=False, stdout=output, stderr=subprocess.STDOUT)
    else:
        if args.v:
            print("  Executing command: {}".format(cmd))
        return subprocess.run(cmd, shell=False, stdout=output, stderr=subprocess.STDOUT)

def random_string(length: int) -> str:
    chars = string.ascii_uppercase
    rnd_str = ""
    for num in range(length):
        rnd_str += random.choice(chars)
    return rnd_str

def make_fat32_compatible(file_path: Path) -> Path:
    # Define a regular expression pattern for illegal characters
    illegal_chars_pattern = re.compile(r'[<>:"/\\|?*\u0000-\u001F\u007F-\u009F]')

    # Replace any illegal characters and unsupported Unicode characters with valid ones
    fat32_compatible_path = []

    # Evaluate each blob of the path
    for element in file_path.parts:
        if element == file_path.anchor:
            fat32_compatible_path.append(element)
        else:
            element_str = ""
            for char in element:
                if illegal_chars_pattern.match(char):
                    element_str += '_'
                elif unicodedata.category(char) in ['Mn', 'Me', 'Cf', 'Cc']:
                    # Ignore combining, enclosing, formatting, and control characters
                    pass
                elif ord(char) > 0xFFFF:
                    # Ignore characters beyond the BMP
                    pass
                else:
                    element_str += char

            # Ensure that the resulting path doesn't exceed the maximum length limit of FAT32
            element_str = element_str.strip()[:255]
            fat32_compatible_path.append(element_str)

    return Path(*fat32_compatible_path)

# Argument custom validators
def remove_empty_from_list(li):
    try:
        while True:
            li.remove('')
    except ValueError:
        pass
    return li
def pop_element_from_list(li, el) -> list:
    try:
        li.remove(el)
    except ValueError:
        pass
    return li

def argcheck_ifm(string) -> list:
    if_mask = string.strip().lower().split(',')
    for el in if_mask:
        if el.startswith('.'):
            el = el[1:]
        if not el.isalnum:
            print('Expected a list of file endings like: jpg,png,bmp,avif,jxl')
            raise argparse.ArgumentError()
    return list(remove_empty_from_list(if_mask))
def argcheck_ofm(string) -> str:
    of_mask = string.strip().lower()
    if of_mask.startswith('.'):
        of_mask = of_mask[1:]
    if not of_mask.isalnum:
        print('Expected a file ending like: jpg')
        raise argparse.ArgumentError()
    return of_mask
def argcheck_cfm(string) -> str:
    cf_mask = string.strip().lower()
    if cf_mask == "*" or cf_mask == "all":
        cf_mask = "*"
    for el in cf_mask.split(','):
        if el.startswith('.'):
            el = el[1:]
        if not el.isalnum:
            print('Expected either \'*\', \'all\' or \
                   a list of file endings like: \'url,png,mp4\'')
            raise argparse.ArgumentError()
    return cf_mask
def argcheck_ms(string) -> int:
    ms_val = 0
    ms_string = string.strip().lower()
    try:
        ms_val = int(ms_string)
    except ValueError:
        units = {"b": 1,
                 "kb": 1000, "k": 1000, "kib": 1024,
                 "mb": 1000**2, "m": 1000**2, "mib": 1024**2,
                 "gb": 1000**3, "g": 1000**3, "gib": 1024**3,
                 "tb": 1000**4, "t": 1000**4, "tib": 1024**4,
                 "pb": 1000**4, "p": 1000**4, "pib": 1024**5}
        number, unit = [element.strip() for element in ms_string.split()]
        ms_val = int(float(number)*units[unit])

    return max(0, ms_val)
def argcheck_cjxlpath(string) -> str:
    cjxlpath = string.strip()
    if 'cjxl' not in cjxlpath: # also check if path exists
        print('Expected a valid path or environment to cjxl binary')
        raise argparse.ArgumentError()
    return cjxlpath
def argcheck_cjxlargs(string) -> list:
    cjxlargs = string.strip().split(' ')
    return list(remove_empty_from_list(cjxlargs))
def argcheck_magickpath(string) -> str:
    magickpath = string.strip()
    if 'magick' not in magickpath: # also check if path exists
        print('Expected a valid path or environment to magick binary')
        raise argparse.ArgumentError()
    return magickpath
def argcheck_preset(string) -> int:
    string = string.lower()
    if string == "visual_lossless":
        return 1
    elif string == "true_lossless":
        return 2
    elif string == "balanced":
        return 3
    elif string == "":
        return 0
    else:
        print('Invalid Preset specified')
        raise argparse.ArgumentError()

# Argument handling
try:
    descrp = textwrap.dedent('''\
            Copys an input directory to a destination and converts applicable files to one desired output format. By default pictures are converted and any other files such as videos are copied to the new destination.

    --Example usages--

    Simple conversion to balanced preset:
    ./picturebatchconverter.py input-dir output-dir

    Visually Lossless conversion:
    ./picturebatchconverter.py --preset visual_lossless input-dir output-dir

    True Lossless conversion:
    ./picturebatchconverter.py --preset true_lossless input-dir output-dir

    Using a custom cjxl version from a container
    ./picturebatchconverter.py -v -cjxlpath "podman run --rm -v $PWD:/temp/ rando/cjxl" /temp/music-album /temp/out
    ''')
    parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter,
                                     description=descrp)

    parser.add_argument("input_dir", type=Path, help="path to input folder. Use \\ or \" for names with spaces")
    parser.add_argument("output_dir", type=Path, help="output folder. Use \\ or \" for names with spaces")
    parser.add_argument("--ignore-dir", type=Path, help="Ignore directory with the specified folder name.")
    parser.add_argument("--ignore-not-empty", action="store_true", help="continue even if the output directory contains files. This overwrites existing files.")
    parser.add_argument("--ignore-not-empty-and-preserve",action="store_true", help="continue even if the output directory contains files. Skip existing files with the same name.")
    parser.add_argument("-ifm", "--inputfilemask", dest="ifm", default="png,apng,jpg,jpeg,jfif,webp,pam,pgm,ppm,bmp,gif,avif,tif,tiff", type=argcheck_ifm, help="Filter mask defining which files will be converted. Other files are copied")
    parser.add_argument("-ofm", "--outputformat", dest="ofm", default="jxl", type=argcheck_ofm, help="Output format of converted files")
    parser.add_argument("-cfm", "--copyfilemask", dest="cfm", default="*", type=argcheck_cfm, help="Do not copy files that match any entry in this list. * or all means do not copy any not-converted files.")
    parser.add_argument("-ms", "--minimumfilesize", dest="minimumfilesize", default="0", type=argcheck_ms, help="Do not convert but copy files that are smaller than given filesize. Example: 100KiB or 1MiB")
    parser.add_argument("-cjxlpath", "--cjxlpath", dest="cjxlpath", default="cjxl", type=argcheck_cjxlpath, help="Path to cjxl binary.")
    parser.add_argument("-cjxlargs", "--cjxlarguments", dest="cjxlargs", type=argcheck_cjxlargs, help="Codec options to submit to cjxl. Choosing a preset overwrites these.")
    parser.add_argument("-magickpath", "--magickpath", dest="magickpath", default="magick", type=argcheck_magickpath, help="Path to magick binary.")
    parser.add_argument("-e", "--cjxleffort", dest="cjxleffort", default=0, type=int, help="CJXL's effort into compressing files. Goes from 1 to 9, low to high.")
    parser.add_argument("-max_workers", default=min(3, os.cpu_count()), type=int, help="Set max parallel converter tasks. By default this is at most four to save memory.")
    parser.add_argument("-v", "--verbose", dest="v", help="Verbose mode", action="store_true")
    parser.add_argument("-vv", "--allverbose", dest="vv", help="Verbose mode for cjxl", action="store_true")
    parser.add_argument("-p", "--preset", default="", type=argcheck_preset,
                        help="Set a preset that overwrites other arguments. Possible values: visual_lossless, true_lossless, balanced")
    parser.add_argument("-fat", "--fat32-compatible", dest="fat", help="Ensure that paths and filenames are compliant with FAT32 filesystems", action="store_true")

    args = parser.parse_args()

except Exception as e:
    print(e)
    exit(-1)

# Check for runtime dependencies
try:
    subprocess.call([ Path(args.cjxlpath), "-h" ], stdout=subprocess.PIPE, shell=False)

except (subprocess.SubprocessError, FileNotFoundError):
    print("This uses the `cjxl` command. You need to make sure that cjxl and its dependent codec libraries are installed.")
    print("If you have tried to use `-cjxlpath` make sure it points to the executable.")
    exit(-1)

if not args.ignore_not_empty and not args.ignore_not_empty_and_preserve and args.output_dir.exists() and len(os.listdir(args.output_dir)) > 0:
    print("Your output directory is not empty. If you continue using --ignore-not-empty-and-preserve existing files with the same name are preserved.")
    exit(-1)

if not args.cjxlargs and not args.preset:
    print("You neither selected a preset nor set any cjxl arguments. Selecting the balanced preset for you...")
    args.preset = 3

# apply preset
if args.preset == 1:
    # visual_lossless
    args.ofm = argcheck_ofm("jxl")
    args.cjxlargs = argcheck_cjxlargs("-d 0.9 --lossless_jpeg=0")

if args.preset == 2:
    # true_lossless
    args.ofm = argcheck_ofm("jxl")
    args.cjxlargs = argcheck_cjxlargs("-d 0 --lossless_jpeg=1")
    if args.cjxleffort == 0:
        args.cjxleffort = 9

if args.preset == 3:
    # balanced
    args.ofm = argcheck_ofm("jxl")
    args.cjxlargs = argcheck_cjxlargs("-q 80 --lossless_jpeg=0")

def copy_file(in_filepath: Path, out_filepath: Path) -> Path:
    if args.fat:
        out_filepath = make_fat32_compatible(out_filepath)
    if args.ignore_not_empty_and_preserve and out_filepath.exists():
        if args.v:
            print("  File {} already exists. Skipping".format(out_filepath))
        return

    shutil.copyfile(in_filepath, out_filepath, follow_symlinks=False)

def convert_file(in_filepath: Path, out_filepath: Path, recursive: bool) -> Path:
    if args.fat:
        out_filepath = make_fat32_compatible(out_filepath)

    if args.ignore_not_empty_and_preserve and out_filepath.exists():
        if args.v:
            print("  File {} already exists. Skipping".format(out_filepath))
        return

    cmd = [ Path(args.cjxlpath), Path(in_filepath), Path(out_filepath) ]
    if args.vv:
        cmd.extend([ '--verbose' ])
    if args.cjxleffort > 0 and args.cjxleffort < 10:
        cmd.extend([ '-e', str(args.cjxleffort) ])
    cmd.extend(args.cjxlargs)
    exec_cmd(cmd)

    if not recursive and not out_filepath.exists():
        if args.v:
            print("  Conversion of {} failed. Using magick to help out".format(out_filepath))
        intermediary_path = Path(out_filepath.parent, out_filepath.stem + ".png")
        cmd = [ Path(args.magickpath), Path(in_filepath), "-render", "-auto-orient", Path(intermediary_path) ]
        exec_cmd(cmd)
        convert_file(intermediary_path, out_filepath, True)
        os.remove(intermediary_path)
        if not out_filepath.exists():
            print("  Unable to read and convert {}.")

# use thread queue for copying to ensure that long copy operations do not starve the conversion task pool
with futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix='copy') as copyexecutor:
    copy_tasks = set()
    # use threadpool for jxl conversion
    with futures.ThreadPoolExecutor(max_workers=args.max_workers, thread_name_prefix='converter') as convertexecutor:
        convert_tasks = set()

        # if you passed ignore_not_empty, we don't want to run into a loop and reconvert pics we already converted
        if args.input_dir.resolve() == args.output_dir.resolve():
            pop_element_from_list(args.ifm, args.ofm)
        
        print("Starting conversion of folder {} to folder {}".format(args.input_dir, args.output_dir))
        print("Files with the endings {} will be converted to {}".format(str(args.ifm), args.ofm))
        print("Codec options to be passed to cjxl: ", str.join(' ', args.cjxlargs))
        print()

        for dirpath, dirnames, filenames in os.walk(args.input_dir):
            if args.v:
                print("Currently evaluating directory " + dirpath)

            ignore_dir = str(args.ignore_dir)
            if ignore_dir != '.' and ignore_dir in dirpath:
                # Skip directory that is meant to be ignored
                continue

            out_dirpath = Path(args.output_dir, Path(dirpath).relative_to(args.input_dir))
            if args.fat:
                out_dirpath = make_fat32_compatible(out_dirpath)

            out_dirpath.mkdir(exist_ok=True)

            for name in sorted(filenames):
                in_filepath = Path(dirpath, name)
                # Evaluate file
                if name.lower().endswith(tuple(args.ifm)):
                    out_filepath = Path(out_dirpath, Path(name).stem + '.' + args.ofm)
                    if args.minimumfilesize > 0 and args.minimumfilesize > in_filepath.stat().st_size:
                        copy_tasks.add(copyexecutor.submit(copy_file, in_filepath, out_filepath))
                    else:
                        convert_tasks.add(convertexecutor.submit(convert_file, in_filepath, out_filepath, False))
                else:
                    if args.cfm == '*':
                        pass
                    elif name.lower().endswith(tuple(args.cfm)):
                        pass
                    else:
                        # Copy file to destination
                        if args.v:
                            print("  copying file: " + str(name))
                        copy_tasks.add(copyexecutor.submit(copy_file, in_filepath, Path(out_dirpath, name)))

                if not args.v:
                    print("{} files to copy, {} files to convert".format(len(copy_tasks), len(convert_tasks)), end='\r')

        print("\nFile evaluation finished")

        # show progress
        if not args.v:
            copies_completed = futures.as_completed(copy_tasks)
            converts_completed = futures.as_completed(convert_tasks)
            current_convert = 0
            for el in converts_completed:
                current_convert += 1
                print("{} out of {} files converted".format(current_convert, len(convert_tasks)), end='\r')

        print("\nCompleted")
