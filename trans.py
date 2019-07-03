from argparse import ArgumentParser, FileType
from datetime import datetime
import json
import os
import sys


def ensureDup(inp, out, inp_key, out_key):
    if out.get(out_key, None) == None:
        out[out_key] = inp.get(inp_key)
        return out
    if out.get(out_key) != inp.get(inp_key):
        print("Input Files do not appear to be for the same release")
        sys.exit(1)
    return out

def url_builder(stream, version, arch, path):
    return "https://builds.coreos.fedoraproject.org/prod/streams/{stream}/builds/{version}/{arch}/{path}".format(
            stream=stream, version=version, arch=arch, path=path)

def get_extension(path, ext_count):
    return ".".join(path.split(".")[-ext_count:])


parser = ArgumentParser()
parser.add_argument("file", type=FileType('r'), nargs='+')
parser.add_argument("--output-file", help="Existing release.json to modify", required=False, default="release.json")
args = parser.parse_args()

out = {}
if args.output_file is not None:
    if os.path.exists(args.output_file):
        with open(args.output_file, 'r') as w:
            out = json.load(w)

for w in args.file:
    input_ = json.load(w)

    # the arch is only present in the ref and in the pkgdiff :(
    arch = input_.get("ref").split("/")[1]

    out = ensureDup(input_, out, "buildid", "release")
    out = ensureDup(input_.get('coreos-assembler.container-config-git'), out, 'branch', 'stream')

    # build the architectures dict
    arch_dict = {"media": {}}
    arch_dict = ensureDup(input_, arch_dict, "ostree-commit", "commit")
    generic_arches = [("qemu", 2), ("metal", 2), ("openstack", 2), ("vmware", 1)]
    for ga, ext_count in generic_arches:
        if input_.get("images", {}).get(ga, None) is not None:
            i = input_.get("images").get(ga)
            ext = get_extension(i.get('path'), ext_count)
            arch_dict['media'][ga] = {
                "artifacts": {
                    ext: {
                        "disk": {
                            "location": url_builder(out.get('stream'), out.get('release'), arch, i.get('path')),
                            "signature": "{}.sig".format(url_builder(out.get('stream'), out.get('release'), arch, i.get('path'))),
                            "sha256": i.get("sha256")
                        }
                    }
                }
            }

    # metal specific additions
    arch_dict["media"]["metal"] = arch_dict["media"]["metal"] or {}
    arch_dict["media"]["metal"]["artifacts"] = arch_dict["media"]["metal"]["artifacts"] or {}
    if input_.get("images", {}).get("iso", None) is not None:
        i = input_.get("images").get("iso")
        arch_dict["media"]["metal"]["artifacts"]["installer.iso"] = {
            "disk": {
                "location": url_builder(out.get('stream'), out.get('release'), arch, i.get('path')),
                "signature": "{}.sig".format(url_builder(out.get('stream'), out.get('release'), arch, i.get('path'))),
                "sha256": i.get("sha256")
            }
        }
    if input_.get("images", {}).get("kernel", None) is not None:
        i = input_.get("images").get("kernel")
        arch_dict["media"]["metal"]["artifacts"]["installer-pxe"] = arch_dict["media"]["metal"]["artifacts"].get("installer-pxe",{})
        arch_dict["media"]["metal"]["artifacts"]["installer-pxe"]["kernel"] = {
            "location": url_builder(out.get('stream'), out.get('release'), arch, i.get('path')),
            "signature": "{}.sig".format(url_builder(out.get('stream'), out.get('release'), arch, i.get('path'))),
            "sha256": i.get("sha256")
        }
    if input_.get("images", {}).get("initramfs", None) is not None:
        i = input_.get("images").get("initramfs")
        arch_dict["media"]["metal"]["artifacts"]["installer-pxe"] = arch_dict["media"]["metal"]["artifacts"].get("installer-pxe", {})
        arch_dict["media"]["metal"]["artifacts"]["installer-pxe"]["initramfs"] = {
            "location": url_builder(out.get('stream'), out.get('release'), arch, i.get('path')),
            "signature": "{}.sig".format(url_builder(out.get('stream'), out.get('release'), arch, i.get('path'))),
            "sha256": i.get("sha256")
        }



    # if architectures as a whole or the individual arch is empty just push our changes
    if out.get('architectures', None) is None or out['architectures'].get(arch, None) is None:
        oa = out.get('architectures', {})
        oa[arch] = arch_dict
        out['architectures'] = oa
    # else check media warning if key present, appending if not
    else:
        out_arch = out['architectures'][arch]
        for media_type, val in arch_dict.get('media').values():
            if media_type not in out_arch['media']:
                out['architectures'][arch]['media'].update({media_type: val})
            elif val == out_arch['media'][media_type]:
                continue
            else:
                print("differing media type detected: input_file '{}', media_type '{}'".format(input_file, media_type))
                sys.exit(1)

if args.output_file is not None:
    with open(args.output_file, 'w') as w:
        json.dump(out, w)
else:
    with open('release.json', 'w') as w:
        json.dump(out, w)
