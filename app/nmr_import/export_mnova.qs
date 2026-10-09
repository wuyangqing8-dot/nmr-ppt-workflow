// Read-only extraction through the installed Mnova 15 scripting toolkit.
function exportWorkflow(input, output) {
    function writeJSON(name, value) {
        var f = new File(output + "/" + name);
        if (!f.open(File.WriteOnly)) { throw "Cannot write " + name; }
        var t = new TextStream(f); t.write(JSON.stringify(value)); f.close();
    }
    var result = {source:input, pages:[], errors:[]};
    try {
        var dw = new DocumentWindow(Application.mainWindow.newWindow());
        if (!serialization.open(input)) { throw "Cannot open input"; }
        dw = new DocumentWindow(Application.mainWindow.activeWindow());
        for (var p=0;p<dw.pageCount();p++) {
            var page = new Page(dw.page(p));
            var row = {index:p,spectra:[],molecules:[]};
            for (var m=0;m<page.itemCount("Molecule");m++) {
                try {
                    var mol = new Molecule(page.item(m,"Molecule"));
                    row.molecules.push({assignments:mol.nmrAssignments(),prediction:mol.nmrPrediction("1H",true),molfile:mol.getMolfile(),smiles:mol.generateSMILES()});
                } catch(e) { row.molecules.push({error:String(e)}); }
            }
            for (var i=0;i<page.itemCount("NMR Spectrum");i++) {
                var spec = new NMRSpectrum(page.item(i,"NMR Spectrum"));
                if (!spec.isValid() || spec.dimCount!==1) { continue; }
                var info={title:spec.title, className:spec.className, params:{},peaks:[],integrals:[]};
                try { info.displayGeometry={left:spec.left,top:spec.top,width:spec.width,height:spec.height,
                    zero:spec.scaleToPage({x:0,y:0}),unit:spec.scaleToPage({x:0,y:0.001}),unitIntensity:0.001}; } catch(e) {info.geometryError=String(e);}
                try {info.multiplets=[];var ml=spec.multiplets();for(var k=0;k<ml.count;k++){var mult=ml.at(k);info.multiplets.push({shift:mult.chemShift,integral:mult.integralValue(),type:mult.type});}}catch(e){info.multipletError=String(e);}
                var names=["Title","Solvent","Spectrometer Frequency","Nucleus","Temperature","Origin"];
                for(var n=0;n<names.length;n++){try{info.params[names[n]]=spec.getParam(names[n]);}catch(e){}}
                var pk=spec.peaks();
                for(var k=0;k<pk.count;k++){var peak=pk.at(k);info.peaks.push({ppm:peak.delta(1),intensity:peak.intensity});}
                var ints=spec.integrals();
                for(var k=0;k<ints.count;k++){var it=ints.at(k);info.integrals.push({min:it.rangeMin(1),max:it.rangeMax(1),raw:it.integralValue(1.0),value:it.integralValue(ints.normValue)});}
                try {
                    var utils=new NMRSpectrumUtils();
                    info.displayBounds=utils.scaleBoundaries(1,[spec]);
                    var bounds=utils.fullScaleBoundaries(1,[spec]);
                    var lo=Math.min(bounds.min,bounds.max),hi=Math.max(bounds.min,bounds.max);
                    var count=utils.getMaxNumberPoints(1,[spec]);
                    var step=(hi-lo)/count;
                    info.trace={min:lo,max:hi,step:step,intensities:spec.rangeIntensities(lo,hi,step)};
                } catch(e){info.traceError=String(e);}
                row.spectra.push(info);
            }
            result.pages.push(row);
        }
        dw.close();
    } catch(e) { result.errors.push(String(e)); }
    writeJSON("mnova_export.json",result);
}
