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
pmtiles_release_root = "overturemaps-tiles-us-west-2-beta"

def get_release_date_time(release_date):
    fmt_str = '%Y-%m-%d'
    return datetime.strptime(release_date, fmt_str)

def process_pmtiles_folder(pmtiles_catalog, s3fs, folder): 
    print ( "Processing" + folder.base_name)
    release_folder_selector = fs.FileSelector(folder.path)
    pmtiles_name = os.path.split(folder.path)[1]
    
    release_files = s3fs.get_file_info(release_folder_selector) 
    extent = pystac.SpatialExtent(bboxes=[[[-180.0, -90.0, 180.0, 90.0]]])
    pmtiles_collection = pystac.Collection(
        id=pmtiles_name, 
        description='PMTiles collection for release ' + pmtiles_name, 
        extent = extent,
        license = "ODbL",
    )

    for pmtiles_file in release_files:
        if (pmtiles_file.is_file):
            stac_item = pystac.Item(
                id=pmtiles_file.base_name,
                geometry=None,
                bbox=None,
                properties={},
                datetime=get_release_date_time(folder.base_name)
            )       

            theme_name = pmtiles_file.base_name.split('.')[0]
            stac_item.add_asset(
                key=theme_name,
                asset=pystac.Asset(
                    href= "./" + folder.base_name + "/" + pmtiles_file.base_name,
                    media_type = 'application/vnd.pmtiles'
                )
            )  
            pmtiles_collection.add_item(stac_item)



    pmtiles_catalog.add_child(pmtiles_collection)


print ('Generating complete catalog for overture PMTiles:')


### Look in a specific release to obtain the themes themselves
filesystem = fs.S3FileSystem(anonymous=True, region="us-west-2")

release_path_selector = fs.FileSelector(pmtiles_release_root + "/");

pmtiles_filelist = filesystem.get_file_info(release_path_selector);

pmtiles_catalog = pystac.Catalog(
    id='pmtiles', 
    href='./build_pmtiles',
    description='This catalog is for the PMTiles data released by overture',
    stac_extensions=['https://stac-extensions.github.io/storage/v2.0.0/schema.json']
);


pmtiles_catalog.extra_fields = {
    'storage:schemes' : {
        'aws': {
            "type": "aws-s3",
            "platform": "https://{bucket}-{region}.s3.amazonaws.com/",
            "bucket": pmtiles_release_root,
            "region": "us-west-2",
            "requester_pays": 'false'
        },
        # 'azure': {
        #     "type": "ms-azure",
        #     "platform": "https://{bucket}-{region}.blob.core.windows.net/release/{release_version}",
        #     "release_version": release_version,
        #     "bucket": "overturemaps",
        #     "region": "westus2",
        #     "requester_pays": 'false'
        # },
    }
}

for item in pmtiles_filelist:
    if (not item.is_file and 'beta' not in item.base_name and 'alpha' not in item.base_name):
        process_pmtiles_folder(pmtiles_catalog, filesystem, item)

pmtiles_catalog.normalize_and_save(root_href = './build_pmtiles', catalog_type=pystac.CatalogType.SELF_CONTAINED);




