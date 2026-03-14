import React from 'react';

const srOnlyStyle = {
  position: 'absolute',
  width: '1px',
  height: '1px',
  padding: '0',
  margin: '-1px',
  overflow: 'hidden',
  clip: 'rect(0, 0, 0, 0)',
  whiteSpace: 'nowrap',
  borderWidth: '0',
};

const ScreenReaderOnly = ({ children, as: Tag = 'span', ...props }) => {
  return (
    <Tag style={srOnlyStyle} {...props}>
      {children}
    </Tag>
  );
};

export default ScreenReaderOnly;
