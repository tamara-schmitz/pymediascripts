#!/usr/bin/python3

# Requires img2pdf package! pip3 install img2pdf
# As well as ImageMagick! (provides `convert`)

# TODO better exception handling when pngs contain alpha

import os
import argparse
import sys
import re
import subprocess
import tempfile
import img2pdf
from concurrent import futures

# Functions for natural sorting
_regex_seps = re.compile(r"[-_:,'\u02bc\u02b9\u02bd\u02be\u02bf\|\[\]\(\)#]")
_regex_volume = re.compile(r"^\s*volume|vol\.?")
_regex_chapter = re.compile(r"\s*chapter|ch\.?")
_regex_spaces = re.compile(r"\s+")
_regex_split = re.compile(r"\s*(\d+(?:\.?\d+)?)\s*")
def atoi(text):
    # handle other obj types
    if not text:
        return ""

    # try conversion to float then pass as string
    try:
        return float(text)
    except ValueError:
        return text

def natural_keys(text):
    '''
    alist.sort(key=natural_keys) sorts in human order
    http://nedbatchelder.com/blog/200712/human_sorting.html
    (See Toothy's implementation in the comments)
    '''
    if isinstance(text, bytes):
        text = os.fsdecode(text)
    text = text.lower()
    # ensure Volumes and Chapter markers come before specials
    text = _regex_volume.sub(" 0V ", text)
    text = _regex_chapter.sub(" 0C ", text)
    # replace special separators and duplicate whitespaces
    text = _regex_seps.sub(" ", text)
    text = _regex_spaces.sub(" ", text).strip()

    return [ atoi(c) for c in _regex_split.split(text) ]

def exec_cmd(cmd, output=None):
    if isinstance(cmd, str):
        cmd = cmd.split(' ')

    if sys.platform == 'win32':
        # TODO this does not appear to work at this time
        si = subprocess.STARTUPINFO()
        si.dwFlags = subprocess.BELOW_NORMAL_PRIORITY_CLASS
        if args.v:
            print("  Executing command: {}".format(cmd))
        return subprocess.run(cmd, shell=False, stdout=output, stderr=subprocess.STDOUT, startupinfo=si)
    elif sys.platform == 'linux':
        cmd.insert(0, "chrt")
        cmd.insert(1, "-b")
        cmd.insert(2, "0")
        cmd.insert(3, "nice")
        cmd.insert(4, "-n19")
        if args.v:
            print("  Executing command: {}".format(cmd))
        return subprocess.run(cmd, shell=False, stdout=output, stderr=subprocess.STDOUT)
    elif sys.platform == 'darwin':
        cmd.insert(0, "nice")
        cmd.insert(1, "-n19")
        if args.v:
            print("  Executing command: {}".format(cmd))
        return subprocess.run(cmd, shell=False, stdout=output, stderr=subprocess.STDOUT)
    else:
        if args.v:
            print("  Executing command: {}".format(cmd))
        return subprocess.run(cmd, shell=False, stdout=output, stderr=subprocess.STDOUT)

# Check for runtime dependencies
try:
    subprocess.call(["convert", "-version"], stdout=subprocess.PIPE, shell=False)

except (subprocess.SubprocessError, FileNotFoundError) as e:
    print(e)
    print("This uses the `convert` command from ImageMagick. You need to make sure that ImageMagick is installed.")
    exit(-1)

# Argument handling
try:
    parser = argparse.ArgumentParser()
    parser.add_argument("in_folder_name", help="path to input folder with subdirs of pngs and jpgs")
    parser.add_argument("out_pdf_name", help="filename of output pdf")
    parser.add_argument("--no_png_alpha_removal", help="Remove alpha channel of all PNGs by converting them before adding to the PDF.", action="store_true")
    parser.add_argument("--no_webp_to_jpg", help="Unless set all WebP images are converted to JPG for higher compatibility with older Ereaders and software", action="store_true")
    parser.add_argument("-v", help="Verbose mode", action="store_true")
    parser.add_argument("--dry", help="Dry run. Useful to check the chapter order.", action="store_true")

    args = parser.parse_args()

except:
    e = sys.exc_info()[0]
    print(e)
    exit(-1)

in_dir = os.fsencode(args.in_folder_name.strip())
out_file = os.fsencode(args.out_pdf_name.strip())


print("Working through directory " + args.in_folder_name + ". Output as " + args.out_pdf_name + ". This may take a while...")

if args.dry:
    args.v = True
    print("This is dry mode. Only printing file order. No processing.")

# Collect input files sorted in list
in_files_list = []
alpha_files_list = []

# use tempdir for image conversion
with tempfile.TemporaryDirectory() as tempdir:
    tempdir_filecounter = 1

    # use threadpool for image conversion
    with futures.ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
        for dirpath, dirnames, filenames in os.walk(in_dir):
            dirnames.sort(key=natural_keys)
            if args.v:
                print("Currently processing dir " + str(dirpath))
            for name in sorted(filenames, key=natural_keys):
                if args.v:
                    print("  File: " + str(name))
                # Evaluate file
                if args.dry:
                    continue
                elif name.endswith((b'.jpg', b'.JPG', b'.jpeg', b'.JPEG')):
                    in_files_list.append(os.path.join(dirpath, name))
                elif name.endswith((b'.png', b'.PNG')):
                    if args.no_png_alpha_removal:
                        in_files_list.append(os.path.join(dirpath, name))
                    else:
                        # Let ImageMagick remove the transparancy from the PNG
                        no_alpha_filename = os.fsencode(os.path.join(tempdir, 'tmp%s.png'%str(tempdir_filecounter)))
                        tempdir_filecounter += 1
                        cmd = [ 'convert', os.path.join(dirpath, name),
                               '-background', 'white', '-alpha', 'remove',
                               '-define', 'png:compression-level=9',
                               '-strip', '-auto-orient',
                               no_alpha_filename ]
                        executor.submit(exec_cmd, cmd)
                        in_files_list.append(no_alpha_filename)
                elif name.endswith((b'.webp', b'.WEBP', b'.WebP')):
                    if args.no_webp_to_jpg:
                        in_files_list.append(os.path.join(dirpath, name))
                    else:
                        # Let ImageMagick convert the file to JPG
                        jpg_of_webp_filename = os.fsencode(os.path.join(tempdir, 'tmp%s.jpg'%str(tempdir_filecounter)))
                        tempdir_filecounter += 1
                        cmd = [ 'convert', os.path.join(dirpath, name),
                               '-background', 'white', '-alpha', 'remove',
                               '-quality', '90', '-colorspace', 'YUV',
                               '-define', 'jpeg:dct-method=float',
                               '-strip', '-auto-orient',
                               jpg_of_webp_filename ]
                        executor.submit(exec_cmd, cmd)
                        in_files_list.append(jpg_of_webp_filename)

    if not args.dry:
        # Create PDF
        print("Creating actual PDF file.")
        with open(out_file, "wb") as outfhandle:
            outfhandle.write(img2pdf.convert(in_files_list, with_pdfrw=False))
