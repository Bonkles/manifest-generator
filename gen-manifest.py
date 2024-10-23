import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.fs as fs
import os
import json
import yaml
import requests

#release_version = "2024-06-13-beta.1"
release_version = "2024-09-18.0"


# Parse the schema-to-release mapping yaml available on the Overture Maps github org, and cross-reference it with the 
def get_schema_version(versionstr): 
    schema_info_url = 'https://raw.githubusercontent.com/OvertureMaps/data/manual-release-metadata/overture_releases.yaml'

    resp = requests.get(schema_info_url)

    if (resp.status_code != 200):
        print("Problem downloading schema-release map, HTTP response code " + resp.status_code)
        exit (1)

    schema_yaml = resp.text
    yaml_content = yaml.safe_load(resp.content)
    for schemaitem in yaml_content: 
        if (schemaitem['release'] == versionstr):
            return schemaitem['schema']

    print ("No schema entry found for this release number, Assuming that we're still using the latest version listed: " + yaml_content[0]['schema'])
    return yaml_content[0]['schema']

#The object that we'll eventually serialize into the release-level manifest
json_dict = {}

json_dict['schema_version'] = get_schema_version(release_version)
json_dict['schema_tag'] = 'https://github.com/OvertureMaps/schema/releases/tag/v' + json_dict['schema_version']
json_dict['release_version'] = release_version


def get_type_schema_info(s3fs, filepath):
    dataset = ds.dataset(
        filepath,  filesystem=s3fs
    )

    metadata = dataset.schema.metadata[b'geo']
    meta_str = metadata.decode('utf-8');
    metadata_obj = json.loads(meta_str)
    ret_obj = {}

    ret_obj['schema_version'] = metadata_obj['version'];
    ret_obj['column_names'] = dataset.schema.names
    # Do we need to include/serialize the column formats? 
    # col_formats = dataset.schema.types
    return ret_obj

def get_type_parquet_bbox(s3fs, filepath):
    dataset = ds.dataset(
        filepath, filesystem=s3fs
    )

    metadata = dataset.schema.metadata[b'geo']
    meta_str = metadata.decode('utf-8');
    metadata_obj = json.loads(meta_str)

    bbox = metadata_obj['columns']['geometry']['bbox']

    return bbox    

# Get the name of a fully-qualified s3 blob storage path assuming our 'thing=stuff' format spec
def parse_name(s3_file_path): 
    return os.path.split(s3_file_path)[1].split('=')[1]

# Generate the type-specific blocks that go in the theme-level of the manifest
def process_type(s3fs, type_info, type_name, theme_relative_path):
    type_dict = {}
    type_dict['name'] = type_name;
    print ("Processing " + type_name + " type")
    theme_path_selector = fs.FileSelector(type_info.path)
    rel_path = '/' + os.path.split(type_info.path)[1]
    type_dict['relative_path'] = rel_path
    type_info = s3fs.get_file_info(theme_path_selector)

    files = []
    for type in type_info: 
        type_info_obj = {}
        if (not type.is_file):
            type_filename = parse_name(type.path)
            print ("\t\tProcessing type " + type_name)
        else: 
            # 'type=building'
            type_filename = os.path.split(type.path)[1]
            type_info_obj['name'] = type_filename

            # extract the bbox that covers this particular file's worth of data
            type_info_obj['bbox'] = get_type_parquet_bbox(s3fs, release_path + theme_relative_path + rel_path + "/" + type_filename)

            files.append(type_info_obj)

        get_type_schema_info(s3fs, release_path + theme_relative_path + rel_path)
    type_dict['files'] = files
    return type_dict

# Generate the theme-specific blocks that go in the top-line manifest
def process_theme(s3fs, theme_info, theme_name):
    theme_dict = {}
    theme_dict['name'] = theme_name;
    print ("\tProcessing theme " + theme_name)

    print ("Processing " + theme_name + " theme")
    theme_path_selector = fs.FileSelector(theme_info.path)
    rel_path = '/' + os.path.split(theme_info.path)[1]
    theme_dict['relative_path'] = rel_path
    theme_dict['status'] = '{alpha/beta/release}'
    theme_info = s3fs.get_file_info(theme_path_selector)
    type_info = []

    for type in theme_info:
        if (not type.is_file):
            type_name = parse_name(type.path)
            type_info.append(process_type(filesystem, type, type_name, rel_path))
    
    theme_dict['types'] = type_info
    return theme_dict

print ('Generating release manifest for release ' + release_version)
release_path = "overturemaps-us-west-2/release/" + release_version
json_dict['s3_location'] = release_path

### Look in a specific release to obtain the themes themselves
filesystem = fs.S3FileSystem(anonymous=True, region="us-west-2")

release_path_selector = fs.FileSelector(release_path);

themes_info = filesystem.get_file_info(release_path_selector);

theme_info = []

for theme in themes_info:
    theme_name = parse_name(theme.path) 
    theme_info.append(process_theme(filesystem, theme, theme_name))

json_dict['themes'] = theme_info

json_object = json.dumps(json_dict, indent=4)

with open("sample.json", "w") as outfile:
    outfile.write(json_object)