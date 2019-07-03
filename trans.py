#!/usr/bin/env python3

from argparse import ArgumentParser, FileType
from datetime import datetime
import json
import os


def ensureDup(inp, out, inp_key, out_key):
    if out.get(out_key, None) == None:
        out[out_key] = inp.get(inp_key)
        return out
    if out.get(out_key) != inp.get(inp_key):
        print("Input Files do not appear to be for the same release")
        raise SystemExit(1)
    return out

def url_builder(stream, version, arch, path):
    return f"https://fcos-builds.s3.amazonaws.com/prod/streams/{stream}/builds/{version}/{arch}/{path}"

def get_extension(path, ext_count):
    return ".".join(path.split(".")[-ext_count:])


parser = ArgumentParser()
parser.add_argument("--workdir", help="cosa workdir", required=True)
parser.add_argument("--build-id", help="build id", required=True)
args = parser.parse_args()

outer_dir = os.path.join(args.workdir, "builds", args.build_id)
release_file = os.path.join(outer_dir, "release.json")

out = {}
if os.path.exists(release_file):
    with open(release_file, 'r') as w:
        out = json.load(w)

build_dirs = [os.path.join(outer_dir, arch_dir) for arch_dir in os.listdir(outer_dir) if os.path.isdir(os.path.join(outer_dir, arch_dir))]
files = [os.path.join(build_dir, "meta.json") for build_dir in build_dirs if os.path.exists(os.path.join(build_dir, "meta.json"))]

for f in files:
    with open(f, 'r') as w:
        input_ = json.load(w)

        arch = input_.get("coreos-assembler.basearch")

        out = ensureDup(input_, out, "buildid", "release")
        out = ensureDup(input_.get('coreos-assembler.container-config-git'), out, 'branch', 'stream')

        # build the architectures dict
        arch_dict = {"media": {}}
        arch_dict = ensureDup(input_, arch_dict, "ostree-commit", "commit")
        generic_arches = [("aws", 2), ("qemu", 2), ("metal", 2), ("openstack", 2), ("vmware", 1)]
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

        # AMI specific additions
        if input_.get("amis", None) is not None:
            arch_dict["media"]["aws"] = arch_dict["media"].get("aws", {})
            arch_dict["media"]["aws"]["images"] = arch_dict["media"]["aws"].get("images", {})
            for ami_dict in input_.get("amis"):
                arch_dict["media"]["aws"]["images"][ami_dict["name"]] = {
                    "image": ami_dict["hvm"]
                }

        # metal specific additions
        arch_dict["media"]["metal"] = arch_dict["media"].get("metal", {})
        arch_dict["media"]["metal"]["artifacts"] = arch_dict["media"]["metal"].get("artifacts", {})
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
            for media_type, val in arch_dict.get('media').items():
                if media_type not in out_arch['media']:
                    out['architectures'][arch]['media'].update({media_type: val})
                elif val == out_arch['media'][media_type]:
                    continue
                else:
                    print("differing media type detected: input_file '{}', media_type '{}'".format(input_file, media_type))
                    raise SystemExit(1)

with open(release_file, 'w') as w:
    json.dump(out, w)
