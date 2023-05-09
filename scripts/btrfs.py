import command_utils as cmd
import output_utils as output

from drive_utils import Formattable


class Btrfs:

    def __init__(
        self,
        devices: list[Formattable],
        data_raid: str,
        metadata_raid: str,
        label: str,
        options: str,
        dry_run: bool=False
    ):

        mkfs_command = "mkfs.btrfs"

        if data_raid:
            mkfs_command += f" -d {data_raid}"
        if metadata_raid:
            mkfs_command += f" -m {metadata_raid}"

        if label:
            mkfs_command += f" -L {label}"

        if options:
            mkfs_command += f" {options}"

        for device in devices:
            mkfs_command += f" {device.partition_path}"

        cmd.execute(mkfs_command, dry_run=dry_run)

        for device in devices:
            device.set_as_btrfs_device(label)
        
        self.uuid = devices[0].uuid
        self.devices = devices
        self.label = label
        
        self.subvolumes = {}

        self.dry_run = dry_run
        
    #--------------------------------------------------------------------------
    
    def create_subvolume(
        self,
        subvolume_path: str,
        mountpoint: str,
        compression: str,
        mount_options: list
    ):

        create_subvol = lambda subvol_path : f"btrfs subvolume create {subvol_path}"
        
        split_subvol = subvolume_path.strip("/").split("/")
        i = 0
        for vol in split_subvol:
            if vol not in self.subvolumes:
                if i == 0:
                    self.subvolumes.append(vol)
                    vol_to_add = vol
                else:
                    vol_to_add = "/".join(vol[:i+1])
                    
                self.subvolumes[vol_to_add] = {
                    "mountpoint" : mountpoint,
                    "compression" : compression,
                    "mount-options" : mount_options
                }
                
                cmd.execute(create_subvol(self.subvolumes.keys()[-1]), dry_run=self.dry_run)
            
            i += 1
            
    def mount_subvolume(
        self,
        subvolume_path
    ):
        
        subvol = self.subvolumes[subvolume_path]
        
        mount_command = f"mount -o subvol={subvol}"
        
        if compress := subvol["compression"]:
            mount_command += f",compress={compress}"
        
        if options := subvol["mount-options"]:
            mount_command += ",".join(options)
            
        mount_command += f" /dev/disk/by-uuid/{self.uuid}"
        
        mount_command += f" {subvol['mountpoint']}"
        
        cmd.execute(mount_command, dry_run=self.dry_run)
            
        
        



        