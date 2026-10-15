"""Initial label planning at output scale. Never render-and-repair or blur RGB."""
import numpy as np
from PIL import Image


def tonal_mask(masks, small, black_l, max_ink_diameter=8.):
    """Separate broad tone from complete fine ink features in SOURCE space.

    Keep the existing eight-unit photographic ink/mass threshold at unit source
    scale, rather than moving it with the output target. A small iris or glyph
    stays an ink feature; a large shadow does not become black when shrunk.
    Whole components are retained, so this does not carve spines from masses.
    """
    if '_ink' not in masks:return np.zeros((small.height,small.width),bool)
    from scipy import ndimage as nd
    # Classify the gray candidates themselves. Including genuine black in this
    # connectivity test lets a black backdrop join every thin chrome edge into
    # one enormous component and wrongly turn those fine edges into washes.
    ink=(np.asarray(masks['_ink'])!=0)&(np.asarray(small.convert('L'),np.uint8)>black_l*2.55)
    labels,n=nd.label(ink)
    dist=nd.distance_transform_edt(np.pad(ink,1))[1:-1,1:-1]
    thick=nd.maximum(dist,labels,index=np.arange(1,n+1))*2 if n else np.array([])
    fine=np.r_[False,thick<=max_ink_diameter][labels]
    return ink&~fine

def tonal_ink(masks, small, black_l, api):
    """An ink eligibility mask is not permission to paint every dark gray black.

    Keep genuinely black samples and complete fine ink features. Other broad
    ink-range samples become their existing calibrated color-ladder wash before
    region planning. This decision is independent of the output target size.
    """
    if '_ink' not in masks:return {'pixels':0}
    rgb=np.asarray(small.convert('RGB'),np.uint8)
    protect=tonal_mask(masks,small,black_l,api.K.BLACK_MASS_THICK_PAINT)
    if not protect.any():return {'pixels':0}
    for key in list(masks):
        masks[key]=api.N.bool_img((np.asarray(masks[key])!=0)&~protect)
    # Same quantization used for ordinary true-color washes; never interpolate
    # the source and feed invented edge colors back into classification.
    ladder=np.asarray([api._tc_key((v,v,v))[0] for v in range(256)],np.uint8)
    mapped=ladder[rgb[protect]].astype(np.uint32)
    packed=(mapped[:,0]<<16)|(mapped[:,1]<<8)|mapped[:,2]
    colors,index=np.unique(packed,return_inverse=True)
    palette=np.column_stack((colors>>16,(colors>>8)&255,colors&255))
    yy,xx=np.nonzero(protect)
    for i,c in enumerate(palette):
        key=('rgb',tuple(map(int,c)))
        arr=np.asarray(masks[key])!=0 if key in masks else np.zeros(protect.shape,bool)
        arr=arr.copy();sel=index==i;arr[yy[sel],xx[sel]]=True
        masks[key]=api.N.bool_img(arr)
    return {'pixels':int(protect.sum()),'wash_colors':len(palette),'black_l':black_l}

def coarsen_washes(masks, ppg, api):
    """Resolve subpixel color competition once, BEFORE any loop generation.

    Below half a page pixel per source pixel, vote among already classified
    color labels in <=one-page-pixel cells. The source RGB is unchanged.
    Paper/ink ownership is never overwritten, and all requested wash pixels
    remain owned. At larger scales this is an exact no-op.
    """
    cell=max(1,int(np.floor(.85/ppg)))
    if cell<2:return {'cell_source_px':1,'changed_pixels':0}
    keys=[k for k in masks if isinstance(k,tuple) and k[0]=='rgb']
    if not keys:return {'cell_source_px':cell,'changed_pixels':0}
    h,w=np.asarray(masks[keys[0]]).shape
    owner=np.full((h,w),-1,np.int32)
    for i,key in enumerate(keys):owner[np.asarray(masks[key])!=0]=i
    yy,xx=np.nonzero(owner>=0)
    if not len(yy):return {'cell_source_px':cell,'changed_pixels':0}
    nx=(w+cell-1)//cell;ny=(h+cell-1)//cell
    block=(yy//cell)*nx+xx//cell
    counts=np.bincount(block*len(keys)+owner[yy,xx],minlength=nx*ny*len(keys)).reshape(-1,len(keys))
    winner=counts.argmax(axis=1)
    chosen=winner[block]
    changed=int((chosen!=owner[yy,xx]).sum())
    owner[yy,xx]=chosen
    for i,key in enumerate(keys):masks[key]=api.N.bool_img(owner==i)
    return {'cell_source_px':cell,'cell_page_px':round(cell*ppg,4),'changed_pixels':changed,
            'occupied_cells':int((counts.sum(axis=1)>0).sum())}
