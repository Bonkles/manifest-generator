import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.fs as fs
import os
import json
import yaml
import requests
import pystac
from datetime import datetime

#release_version = "2024-06-13-beta.1"
release_root = "s3://overturemaps-us-west-2/release/"
release_version = "2024-09-18.0"

license_dict = {
    "base": 'ODbL',
    "buildings": 'ODbL',
    "divisions": 'ODbL',
    "transportation":'ODbL',
    "places": 'CDLA Permissive 2.0',
    "addresses": 'Multiple permissive open licenses'
}

# accepts a filename formatted such as 'part-00000-ab657a87-ddf4-44f2-a96c-d573fcab4818-c000.zstd.parquet'
# and just returns the part number string
def part_number_from_file(filename):
    return filename.split('-')[1]

def get_release_date_time():
    release_date_str = release_version.split('.')[0]
    fmt_str = '%Y-%m-%d'
    return datetime.strptime(release_date_str, fmt_str)

# Parse the schema-to-release mapping yaml available on the Overture Maps github org, and cross-reference it with the version string of the data release.
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
def process_type(theme_catalog, s3fs, type_info, type_name, theme_relative_path):
    print ("Processing " + type_name + " type")
    theme_path_selector = fs.FileSelector(type_info.path)
    rel_path = '/' + os.path.split(type_info.path)[1]
    type_info = s3fs.get_file_info(theme_path_selector)
    ## To do: do we need to be more precise with our extent here? 
    extent = pystac.SpatialExtent(bboxes=[[[-180.0, -90.0, 180.0, 90.0]]])
    type_collection = pystac.Collection(
        id=type_name, 
        description='Type information', 
        extent = extent,
        license = 'ODbL',
    )
    for type in type_info: 
        if (not type.is_file):
            type_filename = parse_name(type.path)
            print ("\t\tProcessing type " + type_name)
        else: 
            # 'type=building'
            type_filename = os.path.split(type.path)[1]

            # extract the bbox that covers this particular file's worth of data
            file_path = release_path + theme_relative_path + rel_path + "/" + type_filename
            bbox = get_type_parquet_bbox(s3fs, file_path)

            stac_item = pystac.Item(
                id=part_number_from_file(type_filename),
                geometry=None, 
                bbox=bbox,
                properties={}, 
                datetime=get_release_date_time(),
                href='s3://' + file_path
            )
            stac_item.add_asset(
                key='parquet-'+type_filename,
                asset=pystac.Asset(href= theme_relative_path + rel_path + "/" + type_filename,
                media_type = 'application/vnd.apache.parquet')
            )
            type_collection.add_item(stac_item)
            print ("Asset href: " + file_path)

    schema_info = get_type_schema_info(s3fs, release_path + theme_relative_path + rel_path)
    type_collection.summaries = pystac.Summaries({'schema': schema_info['schema_version'], 'columns' : schema_info['column_names']})

    type_collection.extra_fields


    theme_catalog.add_child(type_collection)
#    print ('Type Collection description: ')
#    type_collection.describe()

# Generate the theme-specific blocks that go in the top-line manifest
def process_theme(release_catalog, s3fs, theme_info, theme_name):
    print ("\tProcessing theme " + theme_name)

    print ("Processing " + theme_name + " theme")
    theme_path_selector = fs.FileSelector(theme_info.path)
    rel_path = '/' + os.path.split(theme_info.path)[1]
    theme_info = s3fs.get_file_info(theme_path_selector)
    type_info = []
    theme_catalog = pystac.Catalog(id=theme_name, description='Theme information', href=rel_path)
    for type in theme_info:
        if (not type.is_file):
            type_name = parse_name(type.path)
            type_info.append(process_type(theme_catalog, filesystem, type, type_name, rel_path))
    release_catalog.add_child(theme_catalog)

#    print("Theme Catalog: " + json.dumps(theme_catalog.to_dict(), indent=4))


print ('Generating release manifest for release ' + release_version)
release_path = "overturemaps-us-west-2/release/" + release_version


### Look in a specific release to obtain the themes themselves
filesystem = fs.S3FileSystem(anonymous=True, region="us-west-2")

release_path_selector = fs.FileSelector(release_path);

themes_info = filesystem.get_file_info(release_path_selector);

theme_info = []

release_catalog = pystac.Catalog(
    id='release', 
    href='./build',
    description='This catalog is for the geoparquet data released as version ' + release_version,
    stac_extensions=['https://stac-extensions.github.io/storage/v2.0.0/schema.json']
);

schema_version = get_schema_version(release_version)

release_catalog.extra_fields = {
    'release:version': release_version,
    'schema:version':  schema_version,
    'schema:tag': 'https://github.com/OvertureMaps/schema/releases/tag/v' + schema_version,
    'storage:schemes' : {
        'aws': {
            "type": "aws-s3",
            "platform": "https://{bucket}-{region}.s3.amazonaws.com/release/{release_version}",
            "release_version": release_version,
            "bucket": "overturemaps",
            "region": "us-west-2",
            "requester_pays": 'false'
        },
        'azure': {
            "type": "ms-azure",
            "platform": "https://{bucket}-{region}.blob.core.windows.net/release/{release_version}",
            "release_version": release_version,
            "bucket": "overturemaps",
            "region": "westus2",
            "requester_pays": 'false'
        },
    }
}

print ("Catalog href: " + release_root + release_version)
for theme in themes_info:
    theme_name = parse_name(theme.path) 
    #for now just short-circuit the process to work on addresses
    if theme_name == 'addresses':
        theme_info.append(process_theme(release_catalog, filesystem, theme, theme_name))

release_catalog.normalize_and_save(root_href = './build', catalog_type=pystac.CatalogType.SELF_CONTAINED);
