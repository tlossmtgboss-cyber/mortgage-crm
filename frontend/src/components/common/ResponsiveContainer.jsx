import { useState, useEffect } from 'react';

export const useIsTablet = () => {
  const [isTablet, setIsTablet] = useState(
    window.innerWidth >= 768 && window.innerWidth < 1024
  );

  useEffect(() => {
    const handleResize = () => {
      setIsTablet(window.innerWidth >= 768 && window.innerWidth < 1024);
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  return isTablet;
};

export const useScreenOrientation = () => {
  const [orientation, setOrientation] = useState(
    window.screen?.orientation?.type ||
    (window.innerWidth > window.innerHeight ? 'landscape-primary' : 'portrait-primary')
  );

  useEffect(() => {
    const handleChange = () => {
      setOrientation(
        window.screen?.orientation?.type ||
        (window.innerWidth > window.innerHeight ? 'landscape-primary' : 'portrait-primary')
      );
    };
    window.addEventListener('orientationchange', handleChange);
    window.addEventListener('resize', handleChange);
    return () => {
      window.removeEventListener('orientationchange', handleChange);
      window.removeEventListener('resize', handleChange);
    };
  }, []);

  return orientation;
};

const ResponsiveContainer = ({ children, className, style }) => {
  return (
    <div className={className} style={style}>
      {children}
    </div>
  );
};

export default ResponsiveContainer;
