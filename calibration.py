'''
Created on Nov 27, 2013

@author: dstokes
'''

def buildSimplePoly(vals):
    """ Construct a simple polynomial function from a range of values, in
        the general form `y=(vals[0]*pow(x,0))+(vals[1]*pow(x,1))+...`.
        Returns a single-argument function.
    """
    f = [vals[0]] if vals[0] != 0 else []
    for p, v in enumerate(vals[1:],1):
        # optimization: x*0 == 0
        if v == 0:
            continue

        # optimization: v is a whole number, do integer math,
        # then make float by adding 0.0
        if v != 1 and int(v) == v:
            v = int(v)
            extra = "+0.0"
        else:
            extra = ""

        # optimization: pow() is more expensive than lots of multiplication
        x = "*".join(["x"]*p)

        # optimization: remove multiplication by 1
        q = "%s*" % v if v != 1 else ""

        f.append("(%s%s%s)" % (q,x,extra))

    s = "lambda x: %s" % ("+".join(map(str,f)))
    return eval(s)


class SimplePoly(object):
    """ A simple calibration polynomial in the general form 
        `y=(coeffs[0]*pow(x,0))+(coeffs[1]*pow(x,1))+...+(coeffs[n]+pow(x,n))`.
        
        @ivar source: The generated source code for the polynomial.
        @ivar coefficients: 
    """
    
    def __init__(self, coeffs, varName="x"):
        """ Construct a simple polynomial function from a range of values, in
            the general form `y=(coeffs[0]*pow(x,0))+(coeffs[1]*pow(x,1))+...`.
            Returns a single-argument function.
        """
        self.coefficients = coeffs
        # f is used to build the lambda
        # strF is used to build the string version
        f = [coeffs[0]] if coeffs[0] != 0 else []
        strF = f[:]
        for p, v in enumerate(coeffs[1:],1):
            # optimization: x*0 == 0
            if v == 0:
                continue
    
            # optimization: v is a whole number, do integer math,
            # then make float by adding 0.0
            if v != 1 and int(v) == v:
                v = int(v)
                extra = "+0.0"
            else:
                extra = ""
    
            # optimization: pow() is more expensive than lots of multiplication
            x = "*".join([varName]*p)
            strX = "pow(%s,%s)" % (varName, p) if p > 1 else varName
    
            # optimization: remove multiplication by 1
            q = "%s*" % v if v != 1 else ""
    
            f.append("(%s%s%s)" % (q,x,extra))
            strF.append("(%s%s)" % (q, strX))
    
        self.source = "lambda x: %s" % ("+".join(map(str,f)))
        self._str = "+".join(map(str,strF))
        self._function = eval(self.source)
        
        
    def __str__(self):
        return self._str
    
    def __repr__(self):
        return "<%s (%s)>" % (self.__class__.__name__, self._str)
    
    def __call__(self, x):
        return self._function(x)
