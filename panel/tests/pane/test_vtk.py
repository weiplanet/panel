# coding: utf-8

from __future__ import absolute_import

import os
import base64
from io import BytesIO
from zipfile import ZipFile

import pytest
import numpy as np

try:
    import vtk
except Exception:
    vtk = None

try:
    import pyvista as pv
except Exception:
    pv = None

from six import string_types
from panel.models.vtk import VTKJSPlot, VTKVolumePlot, VTKAxes, VTKSynchronizedPlot
from panel.pane import Pane, PaneBase, VTKJS, VTKVolume, VTK

vtk_available = pytest.mark.skipif(vtk is None, reason="requires vtk")
pyvista_available = pytest.mark.skipif(pv is None, reason="requires pyvista")


def make_render_window():
    cone = vtk.vtkConeSource()
    coneMapper = vtk.vtkPolyDataMapper()
    coneMapper.SetInputConnection(cone.GetOutputPort())
    coneActor = vtk.vtkActor()
    coneActor.SetMapper(coneMapper)
    ren = vtk.vtkRenderer()
    ren.AddActor(coneActor)
    renWin = vtk.vtkRenderWindow()
    renWin.AddRenderer(ren)
    return renWin

def pyvista_render_window():
    """
    Allow to download and create a more complex example easily
    """
    from pyvista import examples
    sphere = pv.Sphere() #test actor
    globe = examples.load_globe() #test texture
    head = examples.download_head() #test volume
    uniform = examples.load_uniform() #test structured grid
    
    scalars=sphere.points[:, 2]
    sphere._add_point_array(scalars, 'test', set_active=True) #allow to test scalars

    uniform.set_active_scalars("Spatial Cell Data")

    #test datasetmapper
    threshed = uniform.threshold_percent([0.15, 0.50], invert=True)
    bodies = threshed.split_bodies() 
    mapper = vtk.vtkCompositePolyDataMapper2()
    mapper.SetInputDataObject(0, bodies)
    multiblock = vtk.vtkActor()
    multiblock.SetMapper(mapper)

    pl = pv.Plotter()
    pl.add_mesh(globe)
    pl.add_mesh(sphere)
    pl.add_mesh(uniform)
    pl.add_actor(multiblock)
    pl.add_volume(head)
    return pl.ren_win

def make_image_data():
    image_data = vtk.vtkImageData()
    image_data.SetDimensions(3, 4, 5)
    image_data.AllocateScalars(vtk.VTK_DOUBLE, 1)

    dims = image_data.GetDimensions()

    # Fill every entry of the image data with random double
    for z in range(dims[2]):
        for y in range(dims[1]):
            for x in range(dims[0]):
                image_data.SetScalarComponentFromDouble(x, y, z, 0, np.random.rand())
    return image_data


def test_get_vtkjs_pane_type_from_url():
    url = r'https://raw.githubusercontent.com/Kitware/vtk-js/master/Data/StanfordDragon.vtkjs'
    assert PaneBase.get_pane_type(url) is VTKJS


def test_get_vtkjs_pane_type_from_file():
    file = r'StanfordDragon.vtkjs'
    assert PaneBase.get_pane_type(file) is VTKJS


@vtk_available
def test_get_vtk_pane_type_from_render_window():
    assert PaneBase.get_pane_type(vtk.vtkRenderWindow()) is VTK


def test_get_vtkvol_pane_type_from_np_array():
    assert PaneBase.get_pane_type(np.array([]).reshape((0,0,0))) is VTKVolume


@vtk_available
def test_get_vtkvol_pane_type_from_vtk_image():
    image_data = make_image_data()
    assert PaneBase.get_pane_type(image_data) is VTKVolume


def test_vtkjs_pane_from_url(document, comm, tmp_path):
    url = r'https://raw.githubusercontent.com/Kitware/vtk-js/master/Data/StanfordDragon.vtkjs'

    pane = Pane(url)

    # Create pane
    model = pane.get_root(document, comm=comm)
    assert isinstance(model, VTKJSPlot)
    assert pane._models[model.ref['id']][0] is model
    assert isinstance(model.data, string_types)
    
    with BytesIO(base64.b64decode(model.data.encode())) as in_memory:
        with ZipFile(in_memory) as zf:
            filenames = zf.namelist()
            assert len(filenames) == 9
            assert 'StanfordDragon.obj/index.json' in filenames

    # Export Update and Read
    tmpfile = os.path.join(*tmp_path.joinpath('export.vtkjs').parts)
    pane.export_vtkjs(filename=tmpfile)
    with open(tmpfile, 'rb') as  file_exported:
        pane.object = file_exported


@vtk_available
def test_vtk_pane_from_renwin(document, comm):
    renWin = make_render_window()
    pane = VTK(renWin)

    # Create pane
    model = pane.get_root(document, comm=comm)
    assert isinstance(model, VTKSynchronizedPlot)
    assert pane._models[model.ref['id']][0] is model

    # Check array release when actor are removed from scene
    ctx = pane._contexts[model.id]
    assert len(ctx.dataArrayCache.keys()) == 2
    pane.remove_all_actors()
    # Default : 20s before removing arrays
    assert len(ctx.dataArrayCache.keys()) == 2
    # Force 0s for removing arrays
    ctx.checkForArraysToRelease(0)
    assert len(ctx.dataArrayCache.keys()) == 0

    # Cleanup
    pane._cleanup(model)
    assert pane._contexts == {}
    assert pane._models == {}

@vtk_available
def test_vtk_helpers(document, comm):
    renWin1 = make_render_window()
    renWin2 = make_render_window()
    pane1 = VTK(renWin1)
    pane2 = VTK(renWin2)

    # Create pane
    model1 = pane1.get_root(document, comm=comm)
    model2 = pane2.get_root(document, comm=comm)

    # Actors getter
    assert len(pane1.actors) == 1
    assert len(pane2.actors) == 1
    assert pane1.actors[0] is not pane2.actors[0]

    # Actors add
    pane1.add_actors(pane2.actors)
    assert len(pane1.actors) == 2
    assert pane1.actors[1] is pane2.actors[0]

    # Actors remove
    save_actor = pane1.actors[0]
    pane1.remove_actors([pane1.actors[0]])
    assert pane1.actors[0] is pane2.actors[0]

    # Actors remove all
    pane1.add_actors([save_actor])
    assert len(pane1.actors) == 2
    pane1.remove_all_actors()
    assert len(pane1.actors) == 0

    # Connect camera
    save_vtk_camera2 = pane2.vtk_camera
    assert pane1.vtk_camera is not save_vtk_camera2
    pane1.link_camera(pane2)
    assert pane1.vtk_camera is save_vtk_camera2

    # Unconnect camera
    pane2.unlink_camera()
    assert pane2.vtk_camera is not save_vtk_camera2

    # SetBackground
    pane1.set_background(0, 0, 0)
    assert list(renWin1.GetRenderers())[0].GetBackground() == (0, 0, 0)

    # Cleanup
    pane1._cleanup(model1)
    pane2._cleanup(model2)


@pyvista_available
def test_vtk_pane_more_complex(document, comm):
    renWin = pyvista_render_window()
    pane = VTK(renWin)

    # Create pane
    model = pane.get_root(document, comm=comm)
    assert isinstance(model, VTKSynchronizedPlot)
    assert pane._models[model.ref['id']][0] is model

    # add axes
    pane.axes = dict(
        origin = [-5, 5, -2],
        xticker = {'ticks': np.linspace(-5,5,5)},
        yticker = {'ticks': np.linspace(-5,5,5)},
        zticker = {'ticks': np.linspace(-2,2,5),
                   'labels': [''] + [str(int(item)) for item in np.linspace(-2,2,5)[1:]]},
        fontsize = 12,
        digits = 1,
        grid_opacity = 0.5,
        show_grid=True
    )
    assert isinstance(model.axes, VTKAxes)

    # Cleanup
    pane._cleanup(model)
    assert pane._contexts == {}
    assert pane._models == {}


@vtk_available
def test_vtkvol_pane_from_np_array(document, comm):
    # Test empty initialisation
    pane = VTKVolume()
    model = pane.get_root(document, comm=comm)

    pane.object = np.ones((10,10,10))
    from operator import eq
    # Create pane
    assert isinstance(model, VTKVolumePlot)
    assert pane._models[model.ref['id']][0] is model
    assert np.all(np.frombuffer(base64.b64decode(model.data['buffer'].encode())) == 1)
    assert all([eq(getattr(pane, k), getattr(model, k))
                for k in ['slice_i', 'slice_j', 'slice_k']])

    # Test update data
    pane.object = 2*np.ones((10,10,10))
    assert np.all(np.frombuffer(base64.b64decode(model.data['buffer'].encode())) == 2)

    # Test size limitation of date sent
    pane.max_data_size = 0.1 # limit data size to 0.1MB
    # with uint8
    data = (255*np.random.rand(50,50,50)).astype(np.uint8)
    assert data.nbytes/1e6 > 0.1
    pane.object = data
    data_model = np.frombuffer(base64.b64decode(model.data['buffer'].encode()))
    assert data_model.nbytes/1e6 <= 0.1
    # with float64
    data = np.random.rand(50,50,50)
    assert data.nbytes/1e6 > 0.1
    pane.object = data
    data_model = np.frombuffer(base64.b64decode(model.data['buffer'].encode()), dtype=np.float64)
    assert data_model.nbytes/1e6 <= 0.1

    # Test conversion of the slice_i number with subsample array
    param = pane._process_property_change({'slice_i': (np.cbrt(data_model.size)-1)//2})
    assert param == {'slice_i': (50-1)//2}

    # Cleanup
    pane._cleanup(model)
    assert pane._models == {}


@vtk_available
def test_vtkvol_pane_from_image_data(document, comm):
    image_data = make_image_data()
    pane = VTKVolume(image_data)
    from operator import eq
    # Create pane
    model = pane.get_root(document, comm=comm)
    assert isinstance(model, VTKVolumePlot)
    assert pane._models[model.ref['id']][0] is model
    assert all([eq(getattr(pane, k), getattr(model, k))
                for k in ['slice_i', 'slice_j', 'slice_k']])
    # Cleanup
    pane._cleanup(model)
    assert pane._models == {}
