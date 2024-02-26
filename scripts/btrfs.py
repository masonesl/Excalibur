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
        dry_run: bool = False
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
        mount_options: list,
        target_mountpoint: str
    ):

        create_subvol = lambda subvol_path : f"btrfs subvolume create {target_mountpoint}/{subvol_path}"
        
        split_subvol = subvolume_path.strip("/").split("/")
        i = 0
        for vol in split_subvol:
            if vol not in self.subvolumes:
                mp = comp = m_options = None
                
                if i == len(split_subvol) - 1:
                    vol_to_add = subvolume_path
                    mp = mountpoint
                    comp = compression
                    m_options = mount_options
                elif i == 0:
                    vol_to_add = vol
                else:
                    vol_to_add = "/".join(split_subvol[:i+1])
                    
                self.subvolumes[vol_to_add] = {
                    "mountpoint" : mp,
                    "compression" : comp,
                    "mount-options" : m_options
                }
                
                cmd.execute(create_subvol(vol_to_add), dry_run=self.dry_run)
            
            i += 1
            
    #--------------------------------------------------------------------------        
    
    def get_mountpoint(self, subvolume_path):
        if subvolume_path in self.subvolumes:
            return self.subvolumes[subvolume_path]["mountpoint"]
        else:
            return None
            
    #--------------------------------------------------------------------------
            
    def mount_subvolume(
        self,
        subvolume_path: str,
        override_mount: str
    ):
        
        if not self.get_mountpoint(subvolume_path):
            return
        
        subvol = self.subvolumes[subvolume_path]
        
        mount_command = f"mount -m -o subvol={subvolume_path}"
        
        if compress := subvol["compression"]:
            mount_command += f",compress={compress}"
        
        if options := subvol["mount-options"]:
            mount_command += f",{','.join(options)}"
            
        mount_command += f" /dev/disk/by-uuid/{self.uuid}"
        
        mount_command += f" {override_mount}{self.get_mountpoint(subvolume_path)}"
        
        cmd.execute(mount_command, dry_run=self.dry_run)
        
    #--------------------------------------------------------------------------    
    
    def __repr__(self):
        return_str = f"{self.__class__.__name__}("
        for attribute in self.__dict__:
            return_str += f"{attribute}={self.__dict__[attribute]}, "
        return f"{return_str.strip(', ')})"
            
# EOF
