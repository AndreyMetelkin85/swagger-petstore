package io.swagger.petstore.model;

import javax.xml.bind.annotation.XmlElement;
import javax.xml.bind.annotation.XmlRootElement;

@XmlRootElement(name = "PetUpdateRequest")
public class PetUpdateRequest extends PetCreateRequest {
    private Integer version;

    @XmlElement(name = "version")
    public Integer getVersion() {
        return version;
    }

    public void setVersion(final Integer version) {
        this.version = version;
    }
}
