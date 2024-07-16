import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.fs as fs
import os
import json

release_version = "2024-06-13-beta.1"

json_dict = {}

json_dict['version'] = release_version

def parse_name(s3_file_path): 
    return os.path.split(s3_file_path)[1].split('=')[1]

def process_theme(s3fs, theme_info, theme_name):
    print ("Processing " + theme_name + " theme")
    theme_path_selector = fs.FileSelector(theme_info.path)
    theme_info = s3fs.get_file_info(theme_path_selector)

    for type in theme_info: 
        type_name = parse_name(type.path)
        print ("\tProcessing Type " + type_name)

print ('Generating release manifest for release ' + release_version)
release_path = "overturemaps-us-west-2/release/" + release_version +"/"
json_dict['s3_location'] = release_path

### Look in a specific release to obtain the themes themselves
filesystem = fs.S3FileSystem(anonymous=True, region="us-west-2")

release_path_selector = fs.FileSelector(release_path);

themes_info = filesystem.get_file_info(release_path_selector);

theme_names = []

for theme in themes_info:
    theme_name = parse_name(theme.path)     
    theme_names.append(theme_name)
    process_theme(filesystem, theme, theme_name)

json_dict['themes'] = theme_names

json_object = json.dumps(json_dict, indent=4)

with open("sample.json", "w") as outfile:
    outfile.write(json_object)

# dataset = ds.dataset(
#     path, filesystem=fs.S3FileSystem(anonymous=True, region="us-west-2")
# )

